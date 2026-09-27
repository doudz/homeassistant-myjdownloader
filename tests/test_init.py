"""Tests for setting up, unloading and migrating the MyJDownloader integration."""

from unittest.mock import MagicMock

from myjdapi import MYJDAuthFailedException, MYJDConnectionException
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.myjdownloader.const import DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .conftest import TEST_EMAIL, TEST_PASSWORD

DEVICE_ID = "af9d03a21ddb917492dc1af8a6427f11"

# (domain, v1 unique_id, entity_id, v2 unique_id key) as created by v2.5.0.
# v1 unique_ids embed the entity display name, including spaces.
LEGACY_ENTITIES = [
    ("sensor", "myjdownloader_JDownloader MyPC Status_sensor_status", "sensor.jdownloader_mypc_status", "status"),
    ("sensor", "myjdownloader_JDownloader MyPC Download Speed_sensor_download_speed", "sensor.jdownloader_mypc_download_speed", "download_speed"),
    ("sensor", "myjdownloader_JDownloader MyPC Packages_sensor_packages", "sensor.jdownloader_mypc_packages", "packages"),
    ("sensor", "myjdownloader_JDownloader MyPC Links_sensor_links", "sensor.jdownloader_mypc_links", "links"),
    ("switch", "myjdownloader_JDownloader MyPC Pause_switch_pause", "switch.jdownloader_mypc_pause", "pause"),
    ("switch", "myjdownloader_JDownloader MyPC Limit_switch_limit", "switch.jdownloader_mypc_limit", "limit"),
    ("update", "myjdownloader_JDownloader MyPC Update_update", "update.jdownloader_mypc_update", "update"),
]  # fmt: skip
LEGACY_ONLINE = (
    "sensor",
    "myjdownloader_JDownloaders Online_sensor_number",
    "sensor.jdownloaders_online",
)


async def test_setup_and_unload(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_myjdapi: MagicMock
) -> None:
    """Test the entry is set up and unloaded."""
    entry = init_integration
    assert entry.state is ConfigEntryState.LOADED
    assert hass.services.has_service(DOMAIN, "add_links")

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert not hass.services.has_service(DOMAIN, "add_links")
    mock_myjdapi.disconnect.assert_called_once()


async def test_setup_not_ready(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_myjdapi: MagicMock
) -> None:
    """Test a connection error during setup schedules a retry."""
    mock_myjdapi.connect.side_effect = MYJDConnectionException("offline")
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_not_ready_logs_out(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_myjdapi: MagicMock
) -> None:
    """Test the session is closed when setup fails after logging in."""
    mock_myjdapi.update_devices.side_effect = MYJDConnectionException("offline")
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    mock_myjdapi.disconnect.assert_called_once()


async def test_setup_auth_failed(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_myjdapi: MagicMock
) -> None:
    """Test rejected credentials during setup fail the entry."""
    mock_myjdapi.connect.side_effect = MYJDAuthFailedException("MYJD")
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR


async def test_devices(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test the account device and the JDownloader device."""
    entry_id = init_integration.entry_id
    account = device_registry.async_get_device_by_identifier(
        (DOMAIN, f"account_{entry_id}"), entry_id
    )
    jdownloader = device_registry.async_get_device_by_identifier(
        (DOMAIN, DEVICE_ID), entry_id
    )
    assert account is not None
    assert jdownloader is not None
    assert jdownloader.name == "JDownloader MyPC"
    assert jdownloader.via_device_id == account.id


async def test_migrate_v1(
    hass: HomeAssistant,
    mock_myjdapi: MagicMock,
    mock_latest_version: None,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test v1 unique_ids are migrated while entity_ids are kept."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="MyJDownloader",
        data={CONF_EMAIL: " Test@Example.com ", CONF_PASSWORD: TEST_PASSWORD},
        version=1,
    )
    entry.add_to_hass(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, DEVICE_ID)},
        name="JDownloader MyPC",
    )
    for domain, unique_id, entity_id, _ in LEGACY_ENTITIES:
        entity_registry.async_get_or_create(
            domain,
            DOMAIN,
            unique_id,
            suggested_object_id=entity_id.split(".")[1],
            config_entry=entry,
            device_id=device.id,
        )
    domain, unique_id, entity_id = LEGACY_ONLINE
    entity_registry.async_get_or_create(
        domain,
        DOMAIN,
        unique_id,
        suggested_object_id=entity_id.split(".")[1],
        config_entry=entry,
    )

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.version == 2
    assert entry.unique_id == TEST_EMAIL
    for domain, _, entity_id, key in LEGACY_ENTITIES:
        assert (
            entity_registry.async_get_entity_id(domain, DOMAIN, f"{DEVICE_ID}_{key}")
            == entity_id
        )
    assert (
        entity_registry.async_get_entity_id(
            "sensor", DOMAIN, f"{entry.entry_id}_online_count"
        )
        == "sensor.jdownloaders_online"
    )
    # No duplicates were created next to the migrated entities.
    assert not [
        e
        for e in er.async_entries_for_config_entry(entity_registry, entry.entry_id)
        if e.entity_id.endswith("_2")
    ]
    assert hass.states.get("sensor.jdownloader_mypc_status").state == "running"


async def test_migrate_v1_duplicate_account(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_myjdapi: MagicMock,
    mock_latest_version: None,
) -> None:
    """Test a second v1 entry for the same account keeps no unique_id."""
    mock_config_entry.add_to_hass(hass)
    duplicate = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_EMAIL: TEST_EMAIL, CONF_PASSWORD: TEST_PASSWORD},
        version=1,
    )
    duplicate.add_to_hass(hass)

    await hass.config_entries.async_setup(duplicate.entry_id)
    await hass.async_block_till_done()

    assert duplicate.version == 2
    assert duplicate.unique_id is None


async def test_migrate_future_version(
    hass: HomeAssistant, mock_myjdapi: MagicMock
) -> None:
    """Test a downgrade from a future version fails the migration."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_EMAIL: TEST_EMAIL, CONF_PASSWORD: TEST_PASSWORD},
        version=3,
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.MIGRATION_ERROR
