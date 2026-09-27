"""Tests for the MyJDownloader sensor platform."""

from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er


async def test_sensor_states_after_setup(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_device: MagicMock,
) -> None:
    """Test sensor states after initial setup."""
    entry = init_integration

    status_state = hass.states.get("sensor.jdownloader_mypc_status")
    assert status_state is not None
    assert status_state.state == "running"

    speed_state = hass.states.get("sensor.jdownloader_mypc_download_speed")
    assert speed_state is not None
    assert speed_state.state == "2.5"

    online_entries = [
        e
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        if e.unique_id.endswith("_online_count")
    ]
    assert len(online_entries) == 1
    online_entity_id = online_entries[0].entity_id
    online_state = hass.states.get(online_entity_id)
    assert online_state is not None
    assert online_state.state == "1"
    assert online_state.attributes["jdownloaders"] == ["MyPC"]


@pytest.mark.parametrize(
    ("raw_status", "expected_state"),
    [
        ("IDLE", "idle"),
        ("PAUSE", "paused"),
        ("STOPPING", "stopping"),
        ("STOPPED_STATE", "stopped"),
        ("SOMETHING_NEW", STATE_UNKNOWN),
    ],
)
async def test_status_mapping(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_device: MagicMock,
    raw_status: str,
    expected_state: str,
) -> None:
    """Test that raw download controller states map to the correct sensor states."""
    entry = init_integration
    mock_device.downloadcontroller.get_current_state.return_value = raw_status

    coordinator = entry.runtime_data.coordinator
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    status_state = hass.states.get("sensor.jdownloader_mypc_status")
    assert status_state is not None
    assert status_state.state == expected_state


async def test_packages_and_links_disabled_by_default(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_device: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test that packages and links sensors are disabled by default."""
    # init_integration is in signature to set up the integration.

    packages_entry = entity_registry.async_get("sensor.jdownloader_mypc_packages")
    assert packages_entry is not None
    assert packages_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION

    links_entry = entity_registry.async_get("sensor.jdownloader_mypc_links")
    assert links_entry is not None
    assert links_entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION

    # query_packages and query_links should NOT have been called while disabled.
    mock_device.downloads.query_packages.assert_not_called()
    mock_device.downloads.query_links.assert_not_called()


async def test_enabling_packages_sensor(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_device: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test enabling the packages sensor triggers a data fetch."""
    entry = init_integration

    entity_registry.async_update_entity(
        "sensor.jdownloader_mypc_packages", disabled_by=None
    )
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    packages_state = hass.states.get("sensor.jdownloader_mypc_packages")
    assert packages_state is not None
    assert packages_state.state == "1"
    mock_device.downloads.query_packages.assert_called()


async def test_sensor_unavailable_when_offline(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_device: MagicMock,
    mock_myjdapi: MagicMock,
) -> None:
    """Test sensors become unavailable when the device goes offline."""
    entry = init_integration

    mock_myjdapi.list_devices.return_value = []

    coordinator = entry.runtime_data.coordinator
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    status_state = hass.states.get("sensor.jdownloader_mypc_status")
    assert status_state is not None
    assert status_state.state == STATE_UNAVAILABLE

    # Find the online count sensor entity id from the registry.
    online_entries = [
        e
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        if e.unique_id.endswith("_online_count")
    ]
    assert len(online_entries) == 1
    online_entity_id = online_entries[0].entity_id
    online_state = hass.states.get(online_entity_id)
    assert online_state is not None
    assert online_state.state == "0"
