"""Client wrapper around myjdapi, the only module talking to the library."""

import asyncio
from collections.abc import Callable
import logging
import re
from typing import TypedDict

from myjdapi import (
    Myjdapi,
    MYJDAuthFailedException,
    MYJDDeviceNotFoundException,
    MYJDEmailInvalidException,
    MYJDErrorEmailNotConfirmedException,
    MYJDException,
    MYJDMaintenanceException,
    MYJDOfflineException,
    MYJDOverloadException,
    MYJDSessionException,
    MYJDTokenInvalidException,
    MYJDTooManyRequestsException,
)
from myjdapi.myjdapi import Jddevice
import requests

from homeassistant.core import HomeAssistant

from .const import MYJDAPI_APP_KEY

_LOGGER = logging.getLogger(__name__)

AUTH_EXCEPTIONS = (
    MYJDAuthFailedException,
    MYJDEmailInvalidException,
    MYJDErrorEmailNotConfirmedException,
)
SESSION_EXCEPTIONS = (MYJDTokenInvalidException, MYJDSessionException)
OFFLINE_EXCEPTIONS = (MYJDDeviceNotFoundException, MYJDOfflineException)
BACKOFF_EXCEPTIONS = (
    MYJDTooManyRequestsException,
    MYJDOverloadException,
    MYJDMaintenanceException,
)

# myjdapi and requests put the request URL (email, session tokens) and the
# request payload (e.g. download passwords) into their exception messages.
_SECRET_QUERY = re.compile(
    r"(email|sessiontoken|regaintoken|signature|encryptedLoginSecret)=[^&\s'\")]*",
    re.IGNORECASE,
)
_PAYLOAD = re.compile(r"DATA:.*", re.DOTALL)


def _scrub(err: BaseException) -> None:
    """Remove credentials from an exception chain in place.

    The exceptions are chained to the errors raised by this module and end up
    in logs and diagnostics.
    """
    seen: set[int] = set()
    current: BaseException | None = err
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        current.args = tuple(
            _PAYLOAD.sub(
                "DATA: **REDACTED**", _SECRET_QUERY.sub(r"\1=**REDACTED**", arg)
            )
            if isinstance(arg, str)
            else arg
            for arg in current.args
        )
        current = current.__cause__ or current.__context__


class DeviceInfoDict(TypedDict):
    """A JDownloader as listed by the MyJDownloader API."""

    id: str
    name: str
    type: str


class MyJDownloaderError(Exception):
    """Base error of the MyJDownloader client."""


class MyJDownloaderAuthError(MyJDownloaderError):
    """The MyJDownloader account credentials were rejected."""


class MyJDownloaderConnectionError(MyJDownloaderError):
    """The MyJDownloader API or a JDownloader could not be reached."""


class MyJDownloaderDeviceOfflineError(MyJDownloaderConnectionError):
    """The JDownloader is not connected to MyJDownloader."""


class MyJDownloaderBackoffError(MyJDownloaderConnectionError):
    """The MyJDownloader server asks to slow down.

    too_many_requests: the per-account request limit was hit. Otherwise the
    server is overloaded or in maintenance, which a restarting JDownloader
    also reports for its own requests.
    """

    def __init__(self, name: str, *, too_many_requests: bool) -> None:
        """Initialize the error."""
        super().__init__(name)
        self.too_many_requests = too_many_requests


class MyJDownloaderClient:
    """Serialize all myjdapi access and translate its errors.

    myjdapi keeps request id, session tokens and encryption tokens as mutable
    state on one instance, so concurrent calls break each other. Every call
    therefore runs in the executor while holding a lock.
    """

    def __init__(self, hass: HomeAssistant, email: str, password: str) -> None:
        """Initialize the client."""
        self._hass = hass
        self._email = email
        self._password = password
        self._lock = asyncio.Lock()
        self._api = Myjdapi()
        self._api.set_app_key(MYJDAPI_APP_KEY)
        self._devices: dict[str, Jddevice] = {}

    async def async_connect(self) -> None:
        """Log in to MyJDownloader."""
        await self._async_run(self._connect)

    async def async_disconnect(self) -> None:
        """Log out of MyJDownloader, ignoring errors."""
        try:
            await self._async_run(self._api.disconnect)
        except MyJDownloaderError:
            _LOGGER.debug("Error while disconnecting", exc_info=True)
        self._devices.clear()

    async def async_list_devices(self) -> list[DeviceInfoDict]:
        """Return the JDownloaders currently connected to MyJDownloader."""

        def _list() -> list[DeviceInfoDict]:
            self._api.update_devices()
            return list(self._api.list_devices() or [])

        return await self._async_run(self._with_session(_list))

    async def async_device_call[T](
        self, device_id: str, func: Callable[[Jddevice], T]
    ) -> T:
        """Run func with the Jddevice object of the given JDownloader."""

        def _call() -> T:
            return func(self._get_device(device_id))

        try:
            return await self._async_run(self._with_session(_call))
        except MyJDownloaderDeviceOfflineError:
            self._devices.pop(device_id, None)
            raise

    def _connect(self) -> None:
        self._devices.clear()
        self._api.connect(self._email, self._password)

    def _get_device(self, device_id: str) -> Jddevice:
        # Creating a Jddevice does network I/O (direct connection lookup),
        # so instances are cached until the device goes offline.
        if (device := self._devices.get(device_id)) is None:
            device = self._api.get_device(device_id=device_id)
            self._devices[device_id] = device
        return device

    def _with_session[T](self, func: Callable[[], T]) -> Callable[[], T]:
        """Retry func once after renewing an expired session."""

        def _wrapped() -> T:
            if not self._api.is_connected():
                self._connect()
            try:
                return func()
            except SESSION_EXCEPTIONS:
                _LOGGER.debug("Session expired, reconnecting")
                try:
                    self._api.reconnect()
                except MYJDException, requests.RequestException:
                    self._connect()
                return func()

        return _wrapped

    async def _async_run[T](self, func: Callable[[], T]) -> T:
        async with self._lock:
            try:
                return await self._hass.async_add_executor_job(func)
            except (MYJDException, requests.RequestException, ValueError) as err:
                _scrub(err)
                raise self._translate(err) from err

    @staticmethod
    def _translate(err: Exception) -> MyJDownloaderError:
        """Return the client error for a (scrubbed) library error."""
        name = type(err).__name__
        if isinstance(err, AUTH_EXCEPTIONS):
            return MyJDownloaderAuthError(name)
        if isinstance(err, OFFLINE_EXCEPTIONS):
            return MyJDownloaderDeviceOfflineError(name)
        if isinstance(err, BACKOFF_EXCEPTIONS):
            return MyJDownloaderBackoffError(
                name, too_many_requests=isinstance(err, MYJDTooManyRequestsException)
            )
        # Also ValueError: myjdapi raises it when a known direct connection of
        # a device disappears (Jddevice.__update_direct_connections).
        return MyJDownloaderConnectionError(name)
