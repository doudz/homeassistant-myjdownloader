"""Data update coordinators for the MyJDownloader integration."""

from collections.abc import Callable
from dataclasses import dataclass, field
import logging
import re
from typing import Any

from aiohttp import ClientError
from myjdapi.myjdapi import Jddevice

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    MyJDownloaderAuthError,
    MyJDownloaderBackoffError,
    MyJDownloaderClient,
    MyJDownloaderError,
)
from .const import (
    DOMAIN,
    LATEST_VERSION_REGEX,
    LATEST_VERSION_SCAN_INTERVAL,
    LATEST_VERSION_URL,
    QUERY_LINKS,
    QUERY_PACKAGES,
    SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

# JDownloader download controller states -> sensor states
STATUS_MAP = {
    "IDLE": "idle",
    "RUNNING": "running",
    "PAUSE": "paused",
    "STOPPING": "stopping",
    "STOPPED_STATE": "stopped",
}

# Pauses in seconds when the MyJDownloader server asks to slow down. It does
# not document its limits or send a retry time, so back off exponentially up
# to 30 minutes; a successful update starts over.
BACKOFF_INTERVALS = (120, 240, 480, 960, 1800)

# Entity keys whose data is only fetched while such an entity is enabled.
OPTIONAL_KEYS = ("packages", "links")


@dataclass(frozen=True, slots=True, kw_only=True)
class DeviceState:
    """State of one JDownloader."""

    device_id: str
    name: str
    device_type: str
    online: bool = False
    """Listed as connected by MyJDownloader."""
    available: bool = False
    """Online and all state queries succeeded."""
    raw_status: str | None = None
    speed: int | None = None
    """Download speed in bytes per second."""
    limit: bool | None = None
    update_available: bool | None = None
    core_revision: int | None = None
    packages: list[dict[str, Any]] | None = None
    links: list[dict[str, Any]] | None = None

    @property
    def status(self) -> str | None:
        """Return the normalized download controller state."""
        if self.raw_status is None:
            return None
        return STATUS_MAP.get(self.raw_status.upper())


@dataclass(frozen=True, slots=True)
class MyJDownloaderData:
    """Data of all JDownloaders of the account."""

    devices: dict[str, DeviceState] = field(default_factory=dict)

    @property
    def online_devices(self) -> list[DeviceState]:
        """Return the online JDownloaders, sorted by name."""
        return sorted(
            (device for device in self.devices.values() if device.online),
            key=lambda device: device.name,
        )


type MyJDownloaderConfigEntry = ConfigEntry[MyJDownloaderRuntimeData]


@dataclass(slots=True)
class MyJDownloaderRuntimeData:
    """Runtime data of a MyJDownloader config entry."""

    client: MyJDownloaderClient
    coordinator: MyJDownloaderCoordinator
    account_device_id: str
    update_coordinator: JDownloaderLatestVersionCoordinator


class MyJDownloaderCoordinator(DataUpdateCoordinator[MyJDownloaderData]):
    """Fetch the state of all JDownloaders of a MyJDownloader account."""

    config_entry: MyJDownloaderConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: MyJDownloaderConfigEntry,
        client: MyJDownloaderClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
        )
        self.client = client
        # Devices seen before; kept while offline so their entities become
        # unavailable instead of disappearing.
        self._known: dict[str, tuple[str, str]] = {}
        self._backoff_level = 0

    async def _async_setup(self) -> None:
        """Log in and restore the JDownloaders known from earlier runs."""
        device_registry = dr.async_get(self.hass)
        for device in dr.async_entries_for_config_entry(
            device_registry, self.config_entry.entry_id
        ):
            for domain, identifier in device.identifiers:
                if domain == DOMAIN and not identifier.startswith("account_"):
                    name = (device.name or identifier).removeprefix("JDownloader ")
                    self._known[identifier] = (name, device.model or "jd")
        try:
            await self.client.async_connect()
        except MyJDownloaderAuthError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="auth_failed"
            ) from err
        except MyJDownloaderError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
                translation_placeholders={"error": str(err)},
            ) from err

    async def _async_update_data(self) -> MyJDownloaderData:
        """Fetch the device list and the state of every online JDownloader."""
        try:
            online = {
                device["id"]: device
                for device in await self.client.async_list_devices()
            }
        except MyJDownloaderAuthError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="auth_failed"
            ) from err
        except MyJDownloaderBackoffError as err:
            raise self._backoff() from err
        except MyJDownloaderError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="cannot_connect",
                translation_placeholders={"error": str(err)},
            ) from err

        for device_id, info in online.items():
            self._known[device_id] = (info["name"], info["type"])

        wanted = set(self.async_contexts())
        previous = self.data.devices if self.data else {}
        devices: dict[str, DeviceState] = {}
        for device_id, (name, device_type) in self._known.items():
            state = DeviceState(device_id=device_id, name=name, device_type=device_type)
            if device_id in online:
                state = await self._async_fetch_device(
                    state, previous.get(device_id), wanted
                )
            self._log_availability(state, previous.get(device_id))
            devices[device_id] = state
        self._backoff_level = 0
        return MyJDownloaderData(devices=devices)

    def _backoff(self) -> UpdateFailed:
        """Return the error delaying the next update, growing with every call."""
        retry_after = BACKOFF_INTERVALS[
            min(self._backoff_level, len(BACKOFF_INTERVALS) - 1)
        ]
        self._backoff_level += 1
        return UpdateFailed(
            translation_domain=DOMAIN,
            translation_key="rate_limited",
            translation_placeholders={"minutes": str(retry_after // 60)},
            retry_after=retry_after,
        )

    async def _async_fetch_device(
        self,
        state: DeviceState,
        previous: DeviceState | None,
        wanted: set[Any],
    ) -> DeviceState:
        """Query the state of one online JDownloader.

        A failure only marks this JDownloader unavailable, the others keep
        updating.
        """
        device_id = state.device_id
        call = self.client.async_device_call
        try:
            raw_status = await call(
                device_id, lambda d: d.downloadcontroller.get_current_state()
            )
            speed = await call(
                device_id, lambda d: d.downloadcontroller.get_speed_in_bytes()
            )
            toolbar = await call(device_id, lambda d: d.toolbar.get_status())
            update_available = bool(
                await call(device_id, lambda d: d.update.is_update_available())
            )
            core_revision = previous.core_revision if previous else None
            if (
                core_revision is None
                or previous is None
                or previous.update_available != update_available
            ):
                # Jddevice.jd is missing in myjdapi >= 1.1.9, call the endpoint directly.
                core_revision = await call(
                    device_id, lambda d: d.action("/jd/getCoreRevision")
                )
            packages = links = None
            if (device_id, "packages") in wanted:
                packages = await call(
                    device_id, lambda d: d.downloads.query_packages(QUERY_PACKAGES)
                )
            if (device_id, "links") in wanted:
                links = await call(
                    device_id, lambda d: d.downloads.query_links(QUERY_LINKS)
                )
        except MyJDownloaderAuthError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="auth_failed"
            ) from err
        except MyJDownloaderError as err:
            if isinstance(err, MyJDownloaderBackoffError) and err.too_many_requests:
                # The limit applies to the whole account.
                raise self._backoff() from err
            _LOGGER.debug("Failed to update JDownloader %s: %s", state.name, err)
            return DeviceState(
                device_id=device_id,
                name=state.name,
                device_type=state.device_type,
                online=True,
            )

        if raw_status is not None and raw_status.upper() not in STATUS_MAP:
            _LOGGER.debug("Unknown JDownloader state %s", raw_status)
        return DeviceState(
            device_id=device_id,
            name=state.name,
            device_type=state.device_type,
            online=True,
            available=True,
            raw_status=raw_status,
            speed=speed,
            limit=bool(toolbar.get("limit")) if isinstance(toolbar, dict) else None,
            update_available=update_available,
            core_revision=core_revision,
            packages=packages,
            links=links,
        )

    async def async_device_action(
        self, device_id: str, func: Callable[[Jddevice], Any]
    ) -> None:
        """Run an action on a JDownloader and refresh the state afterwards."""
        state = self.data.devices.get(device_id) if self.data else None
        name = state.name if state else device_id
        try:
            await self.client.async_device_call(device_id, func)
        except MyJDownloaderAuthError as err:
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="auth_failed"
            ) from err
        except MyJDownloaderBackoffError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="rate_limited_action"
            ) from err
        except MyJDownloaderError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="action_failed",
                translation_placeholders={"device": name},
            ) from err
        await self.async_request_refresh()

    @staticmethod
    def _log_availability(state: DeviceState, previous: DeviceState | None) -> None:
        """Log once when a JDownloader becomes unavailable or available again."""
        was_available = previous.available if previous else None
        if was_available is True and not state.available:
            _LOGGER.info("JDownloader %s is unavailable", state.name)
        elif was_available is False and state.available:
            _LOGGER.info("JDownloader %s is available again", state.name)


class JDownloaderLatestVersionCoordinator(DataUpdateCoordinator[str | None]):
    """Fetch the latest JDownloader core revision once a day."""

    config_entry: MyJDownloaderConfigEntry

    def __init__(
        self, hass: HomeAssistant, config_entry: MyJDownloaderConfigEntry
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"{DOMAIN}_latest_version",
            update_interval=LATEST_VERSION_SCAN_INTERVAL,
        )

    async def _async_update_data(self) -> str | None:
        """Fetch the latest revision from the JDownloader build page."""
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(LATEST_VERSION_URL) as response:
                response.raise_for_status()
                text = await response.text()
        except (ClientError, TimeoutError) as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="latest_version_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        if match := re.match(LATEST_VERSION_REGEX, "".join(text.split())):
            return match.group(1)
        return None
