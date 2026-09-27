"""The MyJDownloader integration."""

import logging
from typing import Any

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.typing import ConfigType

from .api import MyJDownloaderClient
from .config_flow import account_id
from .const import DOMAIN, TITLE
from .coordinator import (
    JDownloaderLatestVersionCoordinator,
    MyJDownloaderConfigEntry,
    MyJDownloaderCoordinator,
    MyJDownloaderRuntimeData,
)
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.UPDATE,
]

# Suffixes of the v1 unique_ids ("myjdownloader_<entity name>_<suffix>") and
# the entity description keys they map to.
LEGACY_UNIQUE_ID_SUFFIXES = {
    "_sensor_status": "status",
    "_sensor_download_speed": "download_speed",
    "_sensor_packages": "packages",
    "_sensor_links": "links",
    "_switch_pause": "pause",
    "_switch_limit": "limit",
    "_update": "update",
}
LEGACY_ONLINE_COUNT_SUFFIX = "_sensor_number"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the MyJDownloader actions."""
    async_setup_services(hass)
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: MyJDownloaderConfigEntry
) -> bool:
    """Set up MyJDownloader from a config entry."""
    if entry.unique_id is None and any(
        other.unique_id == account_id(entry.data[CONF_EMAIL])
        for other in hass.config_entries.async_entries(DOMAIN)
    ):
        # A duplicate from before 3.0; its entities would clash with the others.
        raise ConfigEntryError(
            translation_domain=DOMAIN, translation_key="duplicate_account"
        )
    client = MyJDownloaderClient(
        hass, entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD]
    )
    coordinator = MyJDownloaderCoordinator(hass, entry, client)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        # A retry creates a new client, do not leave the session behind.
        await client.async_disconnect()
        raise

    # The latest version is informational, a failure must not block the setup.
    update_coordinator = JDownloaderLatestVersionCoordinator(hass, entry)
    await update_coordinator.async_refresh()

    # The account device has to exist before JDownloader devices refer to it.
    account_device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"account_{entry.entry_id}")},
        name=TITLE,
        manufacturer="AppWork GmbH",
        model="MyJDownloader account",
        entry_type=dr.DeviceEntryType.SERVICE,
        configuration_url="https://my.jdownloader.org/",
    )

    entry.runtime_data = MyJDownloaderRuntimeData(
        client=client,
        coordinator=coordinator,
        update_coordinator=update_coordinator,
        account_device_id=account_device.id,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: MyJDownloaderConfigEntry
) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.client.async_disconnect()
    return unload_ok


async def async_remove_config_entry_device(
    hass: HomeAssistant,
    entry: MyJDownloaderConfigEntry,
    device_entry: dr.DeviceEntry,
) -> bool:
    """Allow removing JDownloaders that are not connected to MyJDownloader.

    MyJDownloader only lists online JDownloaders, so an offline one might be
    switched off or deleted. The user decides; online ones are kept.
    """
    coordinator = entry.runtime_data.coordinator
    for domain, identifier in device_entry.identifiers:
        if domain != DOMAIN or identifier.startswith("account_"):
            continue
        state = coordinator.data.devices.get(identifier)
        if state is not None and state.online:
            return False
        coordinator.async_forget_device(identifier)
        return True
    # The account device is removed together with the config entry.
    return False


async def async_migrate_entry(
    hass: HomeAssistant, entry: MyJDownloaderConfigEntry
) -> bool:
    """Migrate old config entries."""
    if entry.version > 2:
        # Downgrade from a future version
        return False

    if entry.version == 1:
        device_registry = dr.async_get(hass)

        @callback
        def _migrate_unique_id(entity: er.RegistryEntry) -> dict[str, Any] | None:
            if entity.unique_id.endswith(LEGACY_ONLINE_COUNT_SUFFIX):
                return {"new_unique_id": f"{entry.entry_id}_online_count"}
            if (
                entity.device_id is None
                or (device := device_registry.async_get(entity.device_id)) is None
            ):
                return None
            device_id = next(
                (value for domain, value in device.identifiers if domain == DOMAIN),
                None,
            )
            if device_id is None:
                return None
            for suffix, key in LEGACY_UNIQUE_ID_SUFFIXES.items():
                if entity.unique_id.endswith(suffix):
                    return {"new_unique_id": f"{device_id}_{key}"}
            return None

        await er.async_migrate_entries(hass, entry.entry_id, _migrate_unique_id)

        # Versions up to 2.4 had an "update available" binary sensor, replaced
        # by the update entity; its registry entries would stay orphaned.
        entity_registry = er.async_get(hass)
        for entity in er.async_entries_for_config_entry(
            entity_registry, entry.entry_id
        ):
            if entity.domain == "binary_sensor" and entity.unique_id.startswith(
                f"{DOMAIN}_"
            ):
                entity_registry.async_remove(entity.entity_id)

        unique_id = entry.unique_id
        if unique_id is None:
            email = account_id(entry.data[CONF_EMAIL])
            if any(
                other.unique_id == email
                for other in hass.config_entries.async_entries(DOMAIN)
            ):
                _LOGGER.warning(
                    "Config entry %s uses the same MyJDownloader account as "
                    "another entry; remove it",
                    entry.entry_id,
                )
            else:
                unique_id = email
        hass.config_entries.async_update_entry(entry, unique_id=unique_id, version=2)
        _LOGGER.debug("Migrated config entry %s to version 2", entry.entry_id)

    return True
