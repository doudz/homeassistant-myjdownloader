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
        self.devices = {}  # store devices currently online

    @Throttle(datetime.timedelta(seconds=SCAN_INTERVAL_SECONDS))
    async def authenticate(self, email, password) -> bool:
        """Authenticate with Myjdapi."""
        try:
            async with self._sem:
                await self._hass.async_add_executor_job(
                    self.myjd.connect, email, password
                )
        except MYJDException as exception:
            _LOGGER.error("Failed to connect to MyJDownloader")
            raise exception
        else:
            return self.myjd.is_connected()

    async def async_query(self, func, *args, **kwargs):
        """Perform query while ensuring sequentiality of API calls."""
        # TODO catch exceptions, retry once with reconnect, then connect, then reauth if invalid_auth
        # TODO maybe with self.myjd.is_connected()
        async with self._sem:
            return await self._hass.async_add_executor_job(func, *args, **kwargs)

    async def async_update_devices(self):
        """Update list of online devices."""

        # We need to reconnect to the API to query the list of active JDownloaders
        await self.async_query(self.myjd.reconnect)  # TODO move to async query
        await self.async_query(self.myjd.update_devices)

        # add Jddevice objects for all online JDownloaders, if not exist
        available_device_infos = await self.async_query(self.myjd.list_devices)
        for device_info in available_device_infos:
            if not device_info["id"] in self.devices.keys():
                _LOGGER.debug("JDownloader (%s) is online", device_info["name"])
                self.devices.update(
                    {
                        device_info["id"]: await self.async_query(
                            self.myjd.get_device, None, device_info["id"]
                        )
                    }
                )
                # TODO create new set of entities for that device, if they don't exist

        # remove JDownloader objects, that are not online anymore
        unavailable_device_ids = [
            device_id
            for device_id in self.devices.keys()
            if device_id not in [device["id"] for device in available_device_infos]
        ]
        for device_id in unavailable_device_ids:
            _LOGGER.debug("JDownloader (%s) is offline", self.devices[device_id].name)
            del self.devices[device_id]

        return self.devices

    def get_device(self, device_id):
        """Return an online device or raise Exception."""
        try:
            return self.devices[device_id]
        except Exception as ex:
            raise Exception(f"JDownloader ({device_id}) not online") from ex


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up MyJDownloader from a config entry."""

    # create data storage
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {DATA_MYJDOWNLOADER_CLIENT: None}

    # initial connection
    hub = MyJDownloaderHub(hass)
    try:
        if not await hub.authenticate(
            entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD]
        ):
            raise ConfigEntryNotReady
    except MYJDException as exception:
        raise ConfigEntryNotReady from exception
    else:
        await hub.async_update_devices()  # get initial list of JDownloaders
        hass.data.setdefault(DOMAIN, {})[entry.entry_id][
            DATA_MYJDOWNLOADER_CLIENT
        ] = hub

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
