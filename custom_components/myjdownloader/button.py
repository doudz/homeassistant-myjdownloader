"""Buttons of the MyJDownloader integration."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from myjdapi.myjdapi import Jddevice

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MyJDownloaderConfigEntry
from .entity import MyJDownloaderDeviceEntity, async_add_device_entities

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class MyJDownloaderButtonEntityDescription(ButtonEntityDescription):
    """Describes a JDownloader button."""

    press_fn: Callable[[Jddevice], Any]


BUTTONS: tuple[MyJDownloaderButtonEntityDescription, ...] = (
    MyJDownloaderButtonEntityDescription(
        key="start_downloads",
        translation_key="start_downloads",
        press_fn=lambda device: device.downloadcontroller.start_downloads(),
    ),
    MyJDownloaderButtonEntityDescription(
        key="stop_downloads",
        translation_key="stop_downloads",
        press_fn=lambda device: device.downloadcontroller.stop_downloads(),
    ),
    MyJDownloaderButtonEntityDescription(
        key="run_update_check",
        translation_key="run_update_check",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda device: device.update.run_update_check(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MyJDownloaderConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the MyJDownloader buttons."""
    coordinator = entry.runtime_data.coordinator
    async_add_device_entities(
        coordinator,
        async_add_entities,
        lambda device_id: (
            MyJDownloaderButton(coordinator, device_id, description)
            for description in BUTTONS
        ),
    )


class MyJDownloaderButton(MyJDownloaderDeviceEntity, ButtonEntity):
    """Button of a JDownloader."""

    entity_description: MyJDownloaderButtonEntityDescription

    async def async_press(self) -> None:
        """Press the button."""
        await self.async_device_action(self.entity_description.press_fn)
