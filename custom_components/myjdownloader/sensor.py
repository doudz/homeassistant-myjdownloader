"""Sensors of the MyJDownloader integration."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from myjdapi.myjdapi import Jddevice
import voluptuous as vol

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfDataRate
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import MyJDownloaderError
from .const import (
    ATTR_LINKS,
    ATTR_PACKAGES,
    DOMAIN,
    FIELD_AUTO_EXTRACT,
    FIELD_AUTOSTART,
    FIELD_DESTINATION_FOLDER,
    FIELD_DOWNLOAD_PASSWORD,
    FIELD_EXTRACT_PASSWORD,
    FIELD_LINKS,
    FIELD_OVERWRITE_PACKAGIZER_RULES,
    FIELD_PACKAGE_NAME,
    FIELD_PRIORITY,
    SERVICE_ADD_LINKS,
    SERVICE_RESTART_AND_UPDATE,
    SERVICE_RUN_UPDATE_CHECK,
    SERVICE_START_DOWNLOADS,
    SERVICE_STOP_DOWNLOADS,
)
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

    # Kept until the services are reworked, see modernization plan phase D.
    platform = entity_platform.async_get_current_platform()
    for service in (
        SERVICE_RESTART_AND_UPDATE,
        SERVICE_RUN_UPDATE_CHECK,
        SERVICE_START_DOWNLOADS,
        SERVICE_STOP_DOWNLOADS,
    ):
        platform.async_register_entity_service(service, None, f"async_{service}")
    platform.async_register_entity_service(
        SERVICE_ADD_LINKS,
        {
            vol.Required(FIELD_LINKS): cv.ensure_list(cv.url),
            vol.Required(FIELD_PRIORITY): cv.string,
            vol.Optional(FIELD_PACKAGE_NAME): cv.string,
            vol.Optional(FIELD_AUTOSTART): cv.boolean,
            vol.Optional(FIELD_AUTO_EXTRACT): cv.boolean,
            vol.Optional(FIELD_EXTRACT_PASSWORD): cv.string,
            vol.Optional(FIELD_DOWNLOAD_PASSWORD): cv.string,
            vol.Optional(FIELD_DESTINATION_FOLDER): cv.string,
            vol.Optional(FIELD_OVERWRITE_PACKAGIZER_RULES): cv.boolean,
        },
        "async_add_links",
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

    async def _async_device_action(self, func: Callable[[Jddevice], Any]) -> None:
        """Run an action on the JDownloader and refresh afterwards."""
        try:
            await self.coordinator.client.async_device_call(self._device_id, func)
        except MyJDownloaderError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="action_failed",
                translation_placeholders={"device": self.device_state.name},
            ) from err
        await self.coordinator.async_request_refresh()

    async def async_restart_and_update(self) -> None:
        """Restart and update JDownloader."""
        await self._async_device_action(lambda d: d.update.restart_and_update())

    async def async_run_update_check(self) -> None:
        """Run the update check of JDownloader."""
        await self._async_device_action(lambda d: d.update.run_update_check())

    async def async_start_downloads(self) -> None:
        """Start downloads."""
        await self._async_device_action(
            lambda d: d.downloadcontroller.start_downloads()
        )

    async def async_stop_downloads(self) -> None:
        """Stop downloads."""
        await self._async_device_action(lambda d: d.downloadcontroller.stop_downloads())

    async def async_add_links(
        self,
        links: list[str],
        priority: str,
        auto_extract: bool = False,
        autostart: bool = False,
        destination_folder: str | None = None,
        download_password: str | None = None,
        extract_password: str | None = None,
        overwrite_packagizer_rules: bool = False,
        package_name: str | None = None,
    ) -> None:
        """Add links to the LinkGrabber."""
        # https://my.jdownloader.org/developers/index.html#tag_244
        params = [
            {
                "autoExtract": auto_extract,
                "autostart": autostart,
                "destinationFolder": destination_folder,
                "downloadPassword": download_password,
                "extractPassword": extract_password,
                "links": "\n".join(links),
                "overwritePackagizerRules": overwrite_packagizer_rules,
                "packageName": package_name,
                "priority": priority.upper(),
            }
        ]
        await self._async_device_action(lambda d: d.linkgrabber.add_links(params))
