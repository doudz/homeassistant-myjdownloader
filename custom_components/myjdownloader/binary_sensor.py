"""Binary sensors of the MyJDownloader integration."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MyJDownloaderConfigEntry
from .entity import MyJDownloaderDeviceEntity, async_add_device_entities

PARALLEL_UPDATES = 0

CONNECTED = BinarySensorEntityDescription(
    key="connected",
    translation_key="connected",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    entity_category=EntityCategory.DIAGNOSTIC,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MyJDownloaderConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the MyJDownloader binary sensors."""
    coordinator = entry.runtime_data.coordinator
    async_add_device_entities(
        coordinator,
        async_add_entities,
        lambda device_id: [
            MyJDownloaderConnectedSensor(coordinator, device_id, CONNECTED)
        ],
    )


class MyJDownloaderConnectedSensor(MyJDownloaderDeviceEntity, BinarySensorEntity):
    """Whether a JDownloader is connected to MyJDownloader."""

    @property
    def available(self) -> bool:
        """Stay available while the account can be queried, also when offline."""
        return self.coordinator.last_update_success

    @property
    def is_on(self) -> bool:
        """Return if the JDownloader is connected."""
        return self.device_state.online
