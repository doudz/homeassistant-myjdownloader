"""The MyJDownloader integration."""

from __future__ import annotations

import asyncio
import datetime
import logging

from myjdapi.myjdapi import Myjdapi, MYJDException

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.util import Throttle

from .const import (
    DATA_MYJDOWNLOADER_CLIENT,
    DATA_MYJDOWNLOADER_JDOWNLOADERS,
    DOMAIN,
    MYJDAPI_APP_KEY,
    SCAN_INTERVAL_SECONDS,
    SERVICE_RESTART_AND_UPDATE,
    SERVICE_RUN_UPDATE_CHECK,
    SERVICE_START_DOWNLOADS,
    SERVICE_STOP_DOWNLOADS,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor", "switch"]


class MyJDownloaderHub:
    """A MyJDownloader Hub wrapper class."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the MyJDownloader hub."""
        self._hass = hass
        self._sem = asyncio.Semaphore(1)  # API calls need to be sequential
        self.myjd = Myjdapi()
        self.myjd.set_app_key(MYJDAPI_APP_KEY)

    def authenticate(self, email, password) -> bool:
        """Authenticate with Myjdapi."""
        try:
            self.myjd.connect(email, password)
        except MYJDException as exception:
            _LOGGER.error("Failed to connect to MyJDownloader")
            raise exception
        else:
            return self.myjd.is_connected()

    async def async_query(self, func, *args, **kwargs):
        """Perform query while ensuring sequentiality of API calls."""
        async with self._sem:
            return await self._hass.async_add_executor_job(func, *args, **kwargs)

    @Throttle(datetime.timedelta(seconds=SCAN_INTERVAL_SECONDS))
    def reconnect(self) -> bool:
        """Reconnect to MyJDownloaders."""
        try:
            self.myjd.reconnect()
        except MYJDException as exception:
            _LOGGER.error("Failed to connect to MyJDownloader")
            raise exception
        else:
            return self.myjd.is_connected()

    @Throttle(datetime.timedelta(seconds=SCAN_INTERVAL_SECONDS))
    def update_jdownloaders(self) -> list:
        """Update list of available JDownloaders."""

        # get device list
        try:
            self.myjd.update_devices()
        except MYJDException as exception:
            _LOGGER.error("Failed to query available JDownloaders")
            raise exception

        # get device objects
        jdownloaders = []
        for device_entry in self.myjd.list_devices():
            try:
                jdownloaders.append(self.myjd.get_device(device_id=device_entry["id"]))
            except MYJDException as exception:
                if str(exception).strip() == "Device not found":
                    _LOGGER.warning(
                        "Failed to check JDownloader '%s', %s",
                        device_entry["id"],
                        exception,
                    )
                else:
                    _LOGGER.error("Failed to query JDownloader")
                    raise exception
        return jdownloaders


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up MyJDownloader from a config entry."""

    # create data storage
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        DATA_MYJDOWNLOADER_CLIENT: None,
        DATA_MYJDOWNLOADER_JDOWNLOADERS: [],
    }

    # initial connection
    hub = MyJDownloaderHub(hass)
    try:
        if not await hass.async_add_executor_job(
            hub.authenticate, entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD]
        ):
            raise ConfigEntryNotReady
    except MYJDException as exception:
        raise ConfigEntryNotReady from exception
    else:
        hass.data.setdefault(DOMAIN, {})[entry.entry_id][
            DATA_MYJDOWNLOADER_CLIENT
        ] = hub

    # get list of JDownloaders
    try:
        jdownloaders = await hass.async_add_executor_job(hub.update_jdownloaders)
    except MYJDException as exception:
        raise ConfigEntryNotReady from exception
    else:
        hass.data[DOMAIN][entry.entry_id][
            DATA_MYJDOWNLOADER_JDOWNLOADERS
        ] = jdownloaders

    # setup platforms
    for platform in PLATFORMS:
        hass.async_create_task(
            hass.config_entries.async_forward_entry_setup(entry, platform)
        )

    # Services are defined in MyJDownloaderDeviceEntity and
    # registered in setup of sensor platform.

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    # remove services
    hass.services.async_remove(DOMAIN, SERVICE_RESTART_AND_UPDATE)
    hass.services.async_remove(DOMAIN, SERVICE_RUN_UPDATE_CHECK)
    hass.services.async_remove(DOMAIN, SERVICE_START_DOWNLOADS)
    hass.services.async_remove(DOMAIN, SERVICE_STOP_DOWNLOADS)

    # unload platforms
    unload_ok = all(
        await asyncio.gather(
            *[
                hass.config_entries.async_forward_entry_unload(entry, platform)
                for platform in PLATFORMS
            ]
        )
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
