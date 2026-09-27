"""Update entities of the MyJDownloader integration."""

from typing import Any

from homeassistant.components.update import (
    UpdateEntity,
    UpdateEntityDescription,
    UpdateEntityFeature,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import MyJDownloaderError
from .const import DOMAIN
from .coordinator import (
    JDownloaderLatestVersionCoordinator,
    MyJDownloaderConfigEntry,
    MyJDownloaderCoordinator,
)
from .entity import MyJDownloaderDeviceEntity, async_add_device_entities

PARALLEL_UPDATES = 1

UPDATE = UpdateEntityDescription(
    key="update",
    translation_key="update",
    entity_category=EntityCategory.DIAGNOSTIC,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MyJDownloaderConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the MyJDownloader update entities."""
    coordinator = entry.runtime_data.coordinator
    update_coordinator = entry.runtime_data.update_coordinator
    async_add_device_entities(
        coordinator,
        async_add_entities,
        lambda device_id: [
            MyJDownloaderUpdate(coordinator, update_coordinator, device_id)
        ],
    )


class MyJDownloaderUpdate(MyJDownloaderDeviceEntity, UpdateEntity):
    """Update entity of a JDownloader."""

    _attr_supported_features = UpdateEntityFeature.INSTALL
    _attr_title = "JDownloader"

    def __init__(
        self,
        coordinator: MyJDownloaderCoordinator,
        update_coordinator: JDownloaderLatestVersionCoordinator,
        device_id: str,
    ) -> None:
        """Initialize the update entity."""
        super().__init__(coordinator, device_id, UPDATE)
        self._update_coordinator = update_coordinator

    async def async_added_to_hass(self) -> None:
        """Also listen to the latest version coordinator."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._update_coordinator.async_add_listener(self._handle_coordinator_update)
        )

    @property
    def installed_version(self) -> str | None:
        """Return the JDownloader core revision."""
        revision = self.device_state.core_revision
        return str(revision) if revision is not None else None

    @property
    def latest_version(self) -> str | None:
        """Return the latest available core revision.

        JDownloader itself decides whether an update is available. The build
        page revision is only used to show which revision to expect.
        """
        installed = self.installed_version
        if installed is None or not self.device_state.update_available:
            return installed
        latest = self._update_coordinator.data
        if latest is not None and latest.isdigit() and int(latest) > int(installed):
            return latest
        # An update is available but its revision is unknown.
        return f"{installed}+"

    async def async_install(
        self, version: str | None, backup: bool, **kwargs: Any
    ) -> None:
        """Restart JDownloader and install the update."""
        try:
            await self.coordinator.client.async_device_call(
                self._device_id, lambda d: d.update.restart_and_update()
            )
        except MyJDownloaderError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="action_failed",
                translation_placeholders={"device": self.device_state.name},
            ) from err
        await self.coordinator.async_request_refresh()
