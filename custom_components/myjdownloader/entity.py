"""Base entities for the MyJDownloader integration."""

from collections.abc import Callable, Iterable

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity, EntityDescription
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DeviceState, MyJDownloaderCoordinator


def account_identifier(coordinator: MyJDownloaderCoordinator) -> tuple[str, str]:
    """Return the device identifier of the MyJDownloader account."""
    return (DOMAIN, f"account_{coordinator.config_entry.entry_id}")


def async_add_device_entities(
    coordinator: MyJDownloaderCoordinator,
    async_add_entities: AddConfigEntryEntitiesCallback,
    factory: Callable[[str], Iterable[Entity]],
) -> None:
    """Add entities for every JDownloader, including ones appearing later."""
    known: set[str] = set()

    @callback
    def _async_add_new() -> None:
        new = [
            device_id
            for device_id in coordinator.data.devices
            if device_id not in known
        ]
        if not new:
            return
        known.update(new)
        async_add_entities(
            [entity for device_id in new for entity in factory(device_id)]
        )

    _async_add_new()
    coordinator.config_entry.async_on_unload(
        coordinator.async_add_listener(_async_add_new)
    )


class MyJDownloaderEntity(CoordinatorEntity[MyJDownloaderCoordinator]):
    """Base entity of the MyJDownloader integration."""

    _attr_has_entity_name = True


class MyJDownloaderAccountEntity(MyJDownloaderEntity):
    """Entity of the MyJDownloader account itself."""

    def __init__(
        self,
        coordinator: MyJDownloaderCoordinator,
        description: EntityDescription,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"
        # Created with all details in async_setup_entry.
        self._attr_device_info = DeviceInfo(
            identifiers={account_identifier(coordinator)}
        )


class MyJDownloaderDeviceEntity(MyJDownloaderEntity):
    """Entity of one JDownloader."""

    def __init__(
        self,
        coordinator: MyJDownloaderCoordinator,
        device_id: str,
        description: EntityDescription,
        *,
        fetch_on_demand: bool = False,
    ) -> None:
        """Initialize the entity.

        With fetch_on_demand the coordinator only queries the data for this
        entity's key while the entity is enabled.
        """
        super().__init__(
            coordinator, (device_id, description.key) if fetch_on_demand else None
        )
        self.entity_description = description
        self._device_id = device_id
        self._attr_unique_id = f"{device_id}_{description.key}"
        state = coordinator.data.devices[device_id]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=f"JDownloader {state.name}",
            manufacturer="AppWork GmbH",
            model=state.device_type,
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=f"https://my.jdownloader.org/?deviceId={device_id}#webinterface:downloads",
            via_device_id=coordinator.config_entry.runtime_data.account_device_id,
        )

    @property
    def device_state(self) -> DeviceState:
        """Return the current state of this entity's JDownloader."""
        return self.coordinator.data.devices[self._device_id]

    @property
    def available(self) -> bool:
        """Return if the JDownloader is reachable."""
        return super().available and self.device_state.available
