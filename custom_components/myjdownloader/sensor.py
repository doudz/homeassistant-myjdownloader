"""Sensors of the MyJDownloader integration."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfDataRate
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import ATTR_LINKS, ATTR_PACKAGES
from .coordinator import (
    STATUS_MAP,
    DeviceState,
    MyJDownloaderConfigEntry,
    MyJDownloaderCoordinator,
    MyJDownloaderData,
)
from .entity import (
    MyJDownloaderAccountEntity,
    MyJDownloaderDeviceEntity,
    async_add_device_entities,
)

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class MyJDownloaderSensorEntityDescription(SensorEntityDescription):
    """Describes a JDownloader sensor."""

    value_fn: Callable[[DeviceState], Any]
    attributes_fn: Callable[[DeviceState], dict[str, Any]] | None = None
    fetch_on_demand: bool = False


@dataclass(frozen=True, kw_only=True)
class MyJDownloaderAccountSensorEntityDescription(SensorEntityDescription):
    """Describes a MyJDownloader account sensor."""

    value_fn: Callable[[MyJDownloaderData], Any]
    attributes_fn: Callable[[MyJDownloaderData], dict[str, Any]]


SENSORS: tuple[MyJDownloaderSensorEntityDescription, ...] = (
    MyJDownloaderSensorEntityDescription(
        key="status",
        translation_key="status",
        device_class=SensorDeviceClass.ENUM,
        options=sorted(set(STATUS_MAP.values())),
        value_fn=lambda state: state.status,
    ),
    MyJDownloaderSensorEntityDescription(
        key="download_speed",
        translation_key="download_speed",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.MEGABYTES_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda state: (
            round(state.speed / 1_000_000, 2) if state.speed is not None else None
        ),
    ),
    MyJDownloaderSensorEntityDescription(
        key="packages",
        translation_key="packages",
        entity_registry_enabled_default=False,
        fetch_on_demand=True,
        value_fn=lambda state: (
            len(state.packages) if state.packages is not None else None
        ),
        attributes_fn=lambda state: {ATTR_PACKAGES: state.packages or []},
    ),
    MyJDownloaderSensorEntityDescription(
        key="links",
        translation_key="links",
        entity_registry_enabled_default=False,
        fetch_on_demand=True,
        value_fn=lambda state: len(state.links) if state.links is not None else None,
        attributes_fn=lambda state: {ATTR_LINKS: state.links or []},
    ),
)

ONLINE_COUNT = MyJDownloaderAccountSensorEntityDescription(
    key="online_count",
    translation_key="online_count",
    value_fn=lambda data: len(data.online_devices),
    attributes_fn=lambda data: {
        "jdownloaders": [device.name for device in data.online_devices],
        "jdownloader_ids": [device.device_id for device in data.online_devices],
    },
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MyJDownloaderConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the MyJDownloader sensors."""
    coordinator = entry.runtime_data.coordinator

    async_add_entities([MyJDownloaderAccountSensor(coordinator, ONLINE_COUNT)])
    async_add_device_entities(
        coordinator,
        async_add_entities,
        lambda device_id: (
            MyJDownloaderSensor(coordinator, device_id, description)
            for description in SENSORS
        ),
    )


class MyJDownloaderAccountSensor(MyJDownloaderAccountEntity, SensorEntity):
    """Sensor of the MyJDownloader account."""

    entity_description: MyJDownloaderAccountSensorEntityDescription

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        return self.entity_description.attributes_fn(self.coordinator.data)


class MyJDownloaderSensor(MyJDownloaderDeviceEntity, SensorEntity):
    """Sensor of a JDownloader."""

    entity_description: MyJDownloaderSensorEntityDescription
    # The full package and link lists can be large, keep them out of the recorder.
    _unrecorded_attributes = frozenset({ATTR_PACKAGES, ATTR_LINKS})

    def __init__(
        self,
        coordinator: MyJDownloaderCoordinator,
        device_id: str,
        description: MyJDownloaderSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(
            coordinator,
            device_id,
            description,
            fetch_on_demand=description.fetch_on_demand,
        )

    async def async_added_to_hass(self) -> None:
        """Fetch on-demand data right away instead of waiting for the next poll."""
        await super().async_added_to_hass()
        if (
            self.entity_description.fetch_on_demand
            and self.entity_description.value_fn(self.device_state) is None
        ):
            await self.coordinator.async_request_refresh()

    @property
    def native_value(self) -> Any:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(self.device_state)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the state attributes."""
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self.device_state)
