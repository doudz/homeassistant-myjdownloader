"""MyJDownloader binary sensors."""

import datetime

from myjdapi.myjdapi import Jddevice

from homeassistant.components.binary_sensor import (
    DEVICE_CLASS_PROBLEM,
    BinarySensorEntity,
)

from . import MyJDownloaderHub
from .const import (
    DATA_MYJDOWNLOADER_CLIENT,
    DATA_MYJDOWNLOADER_JDOWNLOADERS,
    DOMAIN,
    SCAN_INTERVAL_SECONDS,
)
from .entities import MyJDownloaderDeviceEntity

SCAN_INTERVAL = datetime.timedelta(seconds=SCAN_INTERVAL_SECONDS)


async def async_setup_entry(hass, entry, async_add_entities, discovery_info=None):
    """Set up the binary sensor using config entry."""
    dev = []
    hub = hass.data[DOMAIN][entry.entry_id][DATA_MYJDOWNLOADER_CLIENT]
    for device in hass.data[DOMAIN][entry.entry_id][DATA_MYJDOWNLOADER_JDOWNLOADERS]:
        dev += [
            MyJDownloaderUpdateAvailableSensor(hub, device),
        ]
    async_add_entities(dev, True)


class MyJDownloaderBinarySensor(MyJDownloaderDeviceEntity, BinarySensorEntity):
    """Defines a MyJDownloader binary sensor."""

    def __init__(
        self,
        hub: MyJDownloaderHub,
        device: Jddevice,
        name_template: str,
        icon: str,
        measurement: str,
        device_class: str = None,
        enabled_default: bool = True,
    ) -> None:
        """Initialize MyJDownloader sensor."""
        self._state = None
        self._device_class = device_class
        self.measurement = measurement

        super().__init__(hub, device, name_template, icon, enabled_default)

    @property
    def unique_id(self) -> str:
        """Return the unique ID for this sensor."""
        return "_".join(
            [
                DOMAIN,
                self._name,
                "binary_sensor",
                self.measurement,
            ]
        )

    @property
    def is_on(self) -> bool:
        """Return the state."""
        return self._state

    @property
    def device_class(self) -> str:
        """Return the device class."""
        return self._device_class


class MyJDownloaderUpdateAvailableSensor(MyJDownloaderBinarySensor):
    """Defines a MyJDownloader update available binary sensor."""

    def __init__(
        self,
        hub: MyJDownloaderHub,
        device: Jddevice,
    ) -> None:
        """Initialize MyJDownloader sensor."""
        super().__init__(
            hub,
            device,
            "JDownloader $device_name Update Available",
            None,
            "update_available",
            DEVICE_CLASS_PROBLEM,
        )

    async def _myjdownloader_update(self) -> None:
        """Update MyJDownloader entity."""
        self._state = await self.hub.async_query(
            self._device.update.is_update_available
        )
