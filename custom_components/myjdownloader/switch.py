"""Switches of the MyJDownloader integration."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from myjdapi.myjdapi import Jddevice

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import MyJDownloaderError
from .const import DOMAIN
from .coordinator import DeviceState, MyJDownloaderConfigEntry
from .entity import MyJDownloaderDeviceEntity, async_add_device_entities

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class MyJDownloaderSwitchEntityDescription(SwitchEntityDescription):
    """Describes a JDownloader switch."""

    is_on_fn: Callable[[DeviceState], bool | None]
    turn_on_fn: Callable[[Jddevice], Any]
    turn_off_fn: Callable[[Jddevice], Any]


SWITCHES: tuple[MyJDownloaderSwitchEntityDescription, ...] = (
    MyJDownloaderSwitchEntityDescription(
        key="pause",
        translation_key="pause",
        is_on_fn=lambda state: (
            state.raw_status.upper() == "PAUSE" if state.raw_status else None
        ),
        turn_on_fn=lambda device: device.downloadcontroller.pause_downloads(True),
        turn_off_fn=lambda device: device.downloadcontroller.pause_downloads(False),
    ),
    MyJDownloaderSwitchEntityDescription(
        key="limit",
        translation_key="limit",
        is_on_fn=lambda state: state.limit,
        turn_on_fn=lambda device: device.toolbar.enable_downloadSpeedLimit(),
        turn_off_fn=lambda device: device.toolbar.disable_downloadSpeedLimit(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MyJDownloaderConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the MyJDownloader switches."""
    coordinator = entry.runtime_data.coordinator
    async_add_device_entities(
        coordinator,
        async_add_entities,
        lambda device_id: (
            MyJDownloaderSwitch(coordinator, device_id, description)
            for description in SWITCHES
        ),
    )


class MyJDownloaderSwitch(MyJDownloaderDeviceEntity, SwitchEntity):
    """Switch of a JDownloader."""

    entity_description: MyJDownloaderSwitchEntityDescription

    @property
    def is_on(self) -> bool | None:
        """Return the state of the switch."""
        return self.entity_description.is_on_fn(self.device_state)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._async_set(self.entity_description.turn_on_fn)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._async_set(self.entity_description.turn_off_fn)

    async def _async_set(self, func: Callable[[Jddevice], Any]) -> None:
        try:
            await self.coordinator.client.async_device_call(self._device_id, func)
        except MyJDownloaderError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="action_failed",
                translation_placeholders={"device": self.device_state.name},
            ) from err
        await self.coordinator.async_request_refresh()
