"""MyJDownloader sensors."""

from __future__ import annotations

import datetime
from typing import Any

from myjdapi.myjdapi import Jddevice

from homeassistant.components.sensor import DOMAIN, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfDataRate
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_platform
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MyJDownloaderHub
from .const import (
    ATTR_LINKS,
    ATTR_PACKAGES,
    DATA_MYJDOWNLOADER_CLIENT,
    DOMAIN as MYJDOWNLOADER_DOMAIN,
    SCAN_INTERVAL_SECONDS,
    SERVICE_RESTART_AND_UPDATE,
    SERVICE_RUN_UPDATE_CHECK,
    SERVICE_START_DOWNLOADS,
    SERVICE_STOP_DOWNLOADS,
)
from .entities import MyJDownloaderDeviceEntity, MyJDownloaderEntity

SCAN_INTERVAL = datetime.timedelta(seconds=SCAN_INTERVAL_SECONDS)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    discovery_info=None,
) -> None:
    """Set up the sensor using config entry."""
    hub = hass.data[MYJDOWNLOADER_DOMAIN][entry.entry_id][DATA_MYJDOWNLOADER_CLIENT]

    # This device-less sensor periodically fetches the list of currently online devices
    async_add_entities([MyJDownloaderJDownloadersOnlineSensor(hub)], True)

    @callback
    def async_add_sensor(devices=hub.devices):
        entities = []

        for device_id in devices:
            if DOMAIN not in hub.devices_platforms[device_id]:
                hub.devices_platforms[device_id].add(DOMAIN)
                entities += [
                    MyJDownloaderDownloadSpeedSensor(hub, device_id),
                    MyJDownloaderPackagesSensor(hub, device_id),
                    MyJDownloaderLinksSensor(hub, device_id),
                    MyJDownloaderStatusSensor(hub, device_id),
                ]

        if entities:
            async_add_entities(entities, True)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, f"{MYJDOWNLOADER_DOMAIN}_new_devices", async_add_sensor
        )
    )

    async_add_sensor(hub.devices)

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


class MyJDownloaderDeviceSensor(MyJDownloaderDeviceEntity, SensorEntity):
    """Defines a MyJDownloader device sensor."""

    def __init__(
        self,
        hub: MyJDownloaderHub,
        device_id: str,
        name_template: str,
        icon: str | None,
        measurement: str,
        unit_of_measurement: str | None,
        state_class: str | None,
        entity_category: EntityCategory | None = None,
        enabled_default: bool = True,
    ) -> None:
        """Initialize MyJDownloader sensor."""
        self._state: str | None = None
        self._unit_of_measurement = unit_of_measurement
        self._state_class = state_class
        self.measurement = measurement
        super().__init__(
            hub, device_id, name_template, icon, entity_category, enabled_default
        )

    @property
    def unique_id(self) -> str:
        """Return the unique ID for this sensor."""
        return "_".join(
            [
                MYJDOWNLOADER_DOMAIN,
                self._name,
                DOMAIN,
                self.measurement,
            ]
        )

    @property
    def native_value(self) -> str | None:
        """Return the native value of the sensor."""
        return self._state

    @property
    def native_unit_of_measurement(self) -> str | None:
        """Return the unit this entity's native value is expressed in."""
        return self._unit_of_measurement

    @property
    def state_class(self) -> str | None:
        """State class of sensor."""
        return self._state_class


class MyJDownloaderSensor(MyJDownloaderEntity):
    """Defines a MyJDownloader sensor entity."""

    def __init__(
        self,
        hub: MyJDownloaderHub,
        name: str,
        icon: str,
        measurement: str,
        unit_of_measurement: str | None,
        state_class: str | None,
        entity_category: EntityCategory | None = None,
        enabled_default: bool = True,
    ) -> None:
        """Initialize MyJDownloader sensor."""
        self._state: str | None = None
        self._unit_of_measurement = unit_of_measurement
        self._state_class = state_class
        self.measurement = measurement
        super().__init__(hub, name, icon, entity_category, enabled_default)

    @property
    def unique_id(self) -> str:
        """Return the unique ID for this sensor."""
        return "_".join(
            [
                MYJDOWNLOADER_DOMAIN,
                self._name,
                DOMAIN,
                self.measurement,
            ]
        )

    @property
    def state(self) -> str | None:
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self) -> str | None:
        """Return the unit this state is expressed in."""
        return self._unit_of_measurement

    @property
    def state_class(self) -> str | None:
        """State class of sensor."""
        return self._state_class


class MyJDownloaderJDownloadersOnlineSensor(MyJDownloaderSensor):
    """Defines a MyJDownloader JDownloaders Online sensor."""

    def __init__(
        self,
        hub: MyJDownloaderHub,
    ) -> None:
        """Initialize MyJDownloader sensor."""
        super().__init__(
            hub, "JDownloaders Online", "mdi:download-multiple", "number", None, None
        )
        self.devices: dict[str, Jddevice] = {}

    async def _myjdownloader_update(self) -> None:
        """Update MyJDownloader entity."""
        await self.hub.async_update_devices()
        self.devices = self.hub.devices
        self._state = str(len(self.devices))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        devices = sorted(self.devices.values(), key=lambda x: x.name)
        return {
            "jdownloaders": [device.name for device in devices],
            "jdownloader_ids": [device.device_id for device in devices],
        }


class MyJDownloaderDownloadSpeedSensor(MyJDownloaderDeviceSensor):
    """Defines a MyJDownloader download speed sensor."""

    def __init__(
        self,
        hub: MyJDownloaderHub,
        device_id: str,
    ) -> None:
        """Initialize MyJDownloader sensor."""
        super().__init__(
            hub,
            device_id,
            "JDownloader $device_name Download Speed",
            "mdi:download",
            "download_speed",
            UnitOfDataRate.MEGABYTES_PER_SECOND,
            SensorStateClass.MEASUREMENT,
        )

    async def _myjdownloader_update(self) -> None:
        """Update MyJDownloader entity."""
        device = self.hub.get_device(self._device_id)
        self._state = round(
            await self.hub.async_query(device.downloadcontroller.get_speed_in_bytes)
            / 1_000_000,
            2,
        )


class MyJDownloaderPackagesSensor(MyJDownloaderDeviceSensor):
    """Defines a MyJDownloader packages sensor."""

    def __init__(
        self,
        hub: MyJDownloaderHub,
        device_id: str,
    ) -> None:
        """Initialize MyJDownloader sensor."""
        self._packages_list: list = []
        super().__init__(
            hub,
            device_id,
            "JDownloader $device_name Packages",
            "mdi:package-down",
            "packages",
            None,
            None,
            None,
            False,
        )

    async def _myjdownloader_update(self) -> None:
        """Update MyJDownloader entity."""
        device = self.hub.get_device(self._device_id)
        self._packages_list = await self.hub.async_query(
            device.downloads.query_packages
        )
        self._state = str(len(self._packages_list))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        return {ATTR_PACKAGES: self._packages_list}


class MyJDownloaderLinksSensor(MyJDownloaderDeviceSensor):
    """Defines a MyJDownloader links sensor."""

    def __init__(
        self,
        hub: MyJDownloaderHub,
        device_id: str,
    ) -> None:
        """Initialize MyJDownloader sensor."""
        self._links_list: list = []
        super().__init__(
            hub,
            device_id,
            "JDownloader $device_name Links",
            "mdi:link-box",
            "links",
            None,
            None,
            None,
            False,
        )

    async def _myjdownloader_update(self) -> None:
        """Update MyJDownloader entity."""
        device = self.hub.get_device(self._device_id)
        self._links_list = await self.hub.async_query(device.downloads.query_links)
        self._state = str(len(self._links_list))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        return {ATTR_LINKS: self._links_list}


class MyJDownloaderStatusSensor(MyJDownloaderDeviceSensor):
    """Defines a MyJDownloader status sensor."""

    STATE_ICONS = {
        "idle": "mdi:stop",
        "running": "mdi:play",
        "paused": "mdi:pause",
        "stopped": "mdi:stop",
    }

    def __init__(
        self,
        hub: MyJDownloaderHub,
        device_id: str,
    ) -> None:
        """Initialize MyJDownloader sensor."""
        super().__init__(
            hub,
            device_id,
            "JDownloader $device_name Status",
            "mdi:play-pause",
            "status",
            None,
            None,
        )

    @property
    def icon(self) -> str | None:
        """Return the mdi icon of the entity."""
        if self._state:
            return MyJDownloaderStatusSensor.STATE_ICONS.get(self._state, self._icon)
        return self._icon

    async def _myjdownloader_update(self) -> None:
        """Update MyJDownloader entity."""
        device = self.hub.get_device(self._device_id)
        status = await self.hub.async_query(device.downloadcontroller.get_current_state)
        status = status.lower()
        status = status.replace("_state", "")  # stopped_state -> stopped
        status = "paused" if status == "pause" else status  # pause -> paused
        self._state = status
