"""Base entitiy classes for MyJDownloader integration."""

import logging
from string import Template
from typing import Any

from myjdapi.myjdapi import Jddevice

from homeassistant.helpers.entity import Entity

from . import MyJDownloaderHub
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class MyJDownloaderEntity(Entity):
    """Defines a MyJDownloader entity."""

    def __init__(
        self,
        hub: MyJDownloaderHub,
        name: str,
        icon: str,
        enabled_default: bool = True,
    ) -> None:
        """Initialize the MyJDownloader entity."""
        self._available = True
        self._enabled_default = enabled_default
        self._icon = icon
        self._name = name
        self.hub = hub

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return self._name

    @property
    def icon(self) -> str:
        """Return the mdi icon of the entity."""
        return self._icon

    @property
    def entity_registry_enabled_default(self) -> bool:
        """Return if the entity should be enabled when first added to the entity registry."""
        return self._enabled_default

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self._available

    async def async_update(self) -> None:
        """Update MyJDownloader entity."""
        if not self.enabled:
            return

        try:
            await self._myjdownloader_update()
            self._available = True
        except Exception:
            if self._available:
                _LOGGER.debug(
                    "An error occurred while updating MyJDownloader sensor",
                    exc_info=True,
                )
            self._available = False

    async def _myjdownloader_update(self) -> None:
        """Update MyJDownloader entity."""
        raise NotImplementedError()


class MyJDownloaderDeviceEntity(MyJDownloaderEntity):
    """Defines a MyJDownloader device entity."""

    def __init__(
        self,
        hub: MyJDownloaderHub,
        device: Jddevice,
        name_template: str,
        icon: str,
        enabled_default: bool = True,
    ) -> None:
        """Initialize the MyJDownloader device entity."""

        self._device = device

        name = Template(name_template).substitute(device_name=self._device.name)
        super().__init__(hub, name, icon, enabled_default)

    @property
    def device_info(self) -> "dict[str, Any]":
        """Return device information about this MyJDownloader instance."""
        return {
            "identifiers": {(DOMAIN, self._device.device_id)},
            "name": f"JDownloader {self._device.name}",
            "manufacturer": "AppWork GmbH",
            "model": self._device.device_type,
            "sw_version": None,  # TODO add version method to upstream Jddevice
            "entry_type": "service",
        }

    # Services are registered in setup of sensor platform.
    def restart_and_update(self):
        """Restart and update JDownloader."""
        self._device.update.restart_and_update()

    def run_update_check(self):
        """Run update check of JDownloader."""
        self._device.update.run_update_check()

    def start_downloads(self):
        """Start downloads."""
        self._device.downloadcontroller.start_downloads()

    def stop_downloads(self):
        """Stop downloads."""
        self._device.downloadcontroller.stop_downloads()
