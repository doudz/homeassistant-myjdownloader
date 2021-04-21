"""MyJDownloader sensors."""

import datetime

from myjdapi.myjdapi import Jddevice

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import DATA_RATE_MEGABYTES_PER_SECOND, STATE_UNKNOWN
from homeassistant.helpers import entity_platform

from . import MyJDownloaderHub
from .const import (
    ATTR_LINKS,
    ATTR_PACKAGES,
    DATA_MYJDOWNLOADER_CLIENT,
    DATA_MYJDOWNLOADER_JDOWNLOADERS,
    DOMAIN,
    SCAN_INTERVAL_SECONDS,
    SERVICE_RESTART_AND_UPDATE,
    SERVICE_RUN_UPDATE_CHECK,
    SERVICE_START_DOWNLOADS,
    SERVICE_STOP_DOWNLOADS,
)
from .entities import MyJDownloaderDeviceEntity

SCAN_INTERVAL = datetime.timedelta(seconds=SCAN_INTERVAL_SECONDS)


async def async_setup_entry(hass, entry, async_add_entities, discovery_info=None):
    """Set up the sensor using config entry."""
    dev = []
    hub = hass.data[DOMAIN][entry.entry_id][DATA_MYJDOWNLOADER_CLIENT]
    for device in hass.data[DOMAIN][entry.entry_id][DATA_MYJDOWNLOADER_JDOWNLOADERS]:
        dev += [
            MyJDownloaderDownloadSpeedSensor(hub, device),
            MyJDownloaderPackagesSensor(hub, device),
            MyJDownloaderLinksSensor(hub, device),
            MyJDownloaderStatusSensor(hub, device),
        ]
    async_add_entities(dev, True)

    # device services
    platform = entity_platform.current_platform.get()
    assert platform is not None

    platform.async_register_entity_service(
        SERVICE_RESTART_AND_UPDATE,
        {},
        "restart_and_update",
    )
    platform.async_register_entity_service(
        SERVICE_RUN_UPDATE_CHECK,
        {},
        "run_update_check",
    )
    platform.async_register_entity_service(
        SERVICE_START_DOWNLOADS,
        {},
        "start_downloads",
    )
    platform.async_register_entity_service(
        SERVICE_STOP_DOWNLOADS,
        {},
        "stop_downloads",
    )


class MyJDownloaderSensor(MyJDownloaderDeviceEntity, SensorEntity):
    """Defines a MyJDownloader sensor."""

    def __init__(
        self,
        hub: MyJDownloaderHub,
        device: Jddevice,
        name_template: str,
        icon: str,
        measurement: str,
        unit_of_measurement: str,
        enabled_default: bool = True,
    ) -> None:
        """Initialize MyJDownloader sensor."""
        self._state = None
        self._unit_of_measurement = unit_of_measurement
        self.measurement = measurement

        super().__init__(hub, device, name_template, icon, enabled_default)

    @property
    def unique_id(self) -> str:
        """Return the unique ID for this sensor."""
        return "_".join(
            [
                DOMAIN,
                self._name,
                "sensor",
                self.measurement,
            ]
        )

    @property
    def state(self) -> str:
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit this state is expressed in."""
        return self._unit_of_measurement


class MyJDownloaderDownloadSpeedSensor(MyJDownloaderSensor):
    """Defines a MyJDownloader download speed sensor."""

    def __init__(
        self,
        hub: MyJDownloaderHub,
        device: Jddevice,
    ) -> None:
        """Initialize MyJDownloader sensor."""
        super().__init__(
            hub,
            device,
            "JDownloader $device_name Download Speed",
            "mdi:download",
            "download_speed",
            DATA_RATE_MEGABYTES_PER_SECOND,
        )

    async def _myjdownloader_update(self) -> None:
        """Update MyJDownloader entity."""
        self._state = round(
            await self.hub.async_query(
                self._device.downloadcontroller.get_speed_in_bytes
            )
            / 1_000_000,
            2,
        )


class MyJDownloaderPackagesSensor(MyJDownloaderSensor):
    """Defines a MyJDownloader packages sensor."""

    def __init__(
        self,
        hub: MyJDownloaderHub,
        device: Jddevice,
    ) -> None:
        """Initialize MyJDownloader sensor."""
        self._download_list = []
        super().__init__(
            hub,
            device,
            "JDownloader $device_name Packages",
            "mdi:download",
            "packages",
            None,
            False,
        )

    @property
    def icon(self) -> str:
        """Return the mdi icon of the entity."""
        return self._icon

    async def _myjdownloader_update(self) -> None:
        """Update MyJDownloader entity."""
        self._packages_list = await self.hub.async_query(
            self._device.downloads.query_packages
        )
        self._state = len(self._packages_list)

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {ATTR_PACKAGES: self._packages_list}


class MyJDownloaderLinksSensor(MyJDownloaderSensor):
    """Defines a MyJDownloader links sensor."""

    def __init__(
        self,
        hub: MyJDownloaderHub,
        device: Jddevice,
    ) -> None:
        """Initialize MyJDownloader sensor."""
        self._download_list = []
        super().__init__(
            hub,
            device,
            "JDownloader $device_name Links",
            "mdi:download",
            "links",
            None,
            False,
        )

    @property
    def icon(self) -> str:
        """Return the mdi icon of the entity."""
        return self._icon

    async def _myjdownloader_update(self) -> None:
        """Update MyJDownloader entity."""
        self._links_list = await self.hub.async_query(
            self._device.downloads.query_links
        )
        self._state = len(self._links_list)

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {ATTR_LINKS: self._links_list}


class MyJDownloaderStatusSensor(MyJDownloaderSensor):
    """Defines a MyJDownloader status sensor."""

    STATE_ICONS = {
        "idle": "mdi:stop",
        "running": "mdi:play",
        "pause": "mdi:pause",
        "stopped": "mdi:stop",
    }

    def __init__(
        self,
        hub: MyJDownloaderHub,
        device: Jddevice,
    ) -> None:
        """Initialize MyJDownloader sensor."""
        super().__init__(
            hub,
            device,
            "JDownloader $device_name Status",
            "mdi:play-pause",
            "status",
            None,
        )

    @property
    def icon(self) -> str:
        """Return the mdi icon of the entity."""
        return MyJDownloaderStatusSensor.STATE_ICONS.get(self._state, self._icon)

    async def _myjdownloader_update(self) -> None:
        """Update MyJDownloader entity."""
        status = (
            await self.hub.async_query(
                self._device.downloadcontroller.get_current_state
            )
        ).lower()
        if not status:
            status = STATE_UNKNOWN
        else:
            status = status.replace("_state", "")  # stopped_state -> stopped
        self._state = status
