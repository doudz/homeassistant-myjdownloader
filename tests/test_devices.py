"""Tests for the JDownloader device lifecycle."""

import inspect
from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.myjdownloader.const import DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component

JDOWNLOADER_ID = "af9d03a21ddb917492dc1af8a6427f11"
STATUS = "sensor.jdownloader_mypc_status"


def _device(
    device_registry: dr.DeviceRegistry, entry: MockConfigEntry, identifier: str
) -> dr.DeviceEntry:
    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, identifier), entry.entry_id
    )
    assert device is not None
    return device


async def _refresh(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()


async def _remove_device(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    device: dr.DeviceEntry,
    entry: MockConfigEntry,
) -> bool:
    assert await async_setup_component(hass, "config", {})
    client = await hass_ws_client(hass)
    # 2026.9 replaced config/device_registry/remove_config_entry with
    # config/device_registry/remove; both call async_remove_config_entry_device.
    if len(inspect.signature(client.remove_device).parameters) == 2:
        response = await client.remove_device(device.id, entry.entry_id)
    else:
        response = await client.remove_device(device.id)
    return bool(response["success"])


async def test_sw_version(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test the core revision is the device software version."""
    device = _device(device_registry, init_integration, JDOWNLOADER_ID)
    assert device.sw_version == "48000"


async def test_online_device_cannot_be_removed(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    init_integration: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test a connected JDownloader is kept."""
    device = _device(device_registry, init_integration, JDOWNLOADER_ID)
    assert not await _remove_device(hass, hass_ws_client, device, init_integration)
    assert device_registry.async_get(device.id) is not None


async def test_removed_device_back_before_next_refresh(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    init_integration: MockConfigEntry,
    mock_myjdapi: MagicMock,
    device_registry: dr.DeviceRegistry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test entities are recreated when the device returns before a refresh."""
    device_list = mock_myjdapi.list_devices.return_value
    mock_myjdapi.list_devices.return_value = []
    await _refresh(hass, init_integration)
    device = _device(device_registry, init_integration, JDOWNLOADER_ID)
    assert await _remove_device(hass, hass_ws_client, device, init_integration)
    await hass.async_block_till_done()

    mock_myjdapi.list_devices.return_value = device_list
    await _refresh(hass, init_integration)

    assert hass.states.get(STATUS).state == "running"
    assert "Unexpected error" not in caplog.text


async def test_account_device_cannot_be_removed(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    init_integration: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test the account device is only removed with the config entry."""
    device = _device(
        device_registry, init_integration, f"account_{init_integration.entry_id}"
    )
    assert not await _remove_device(hass, hass_ws_client, device, init_integration)


async def test_offline_device_removed_and_rediscovered(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    init_integration: MockConfigEntry,
    mock_myjdapi: MagicMock,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test an offline JDownloader can be removed and comes back when online."""
    device_list = mock_myjdapi.list_devices.return_value
    mock_myjdapi.list_devices.return_value = []
    await _refresh(hass, init_integration)

    device = _device(device_registry, init_integration, JDOWNLOADER_ID)
    assert await _remove_device(hass, hass_ws_client, device, init_integration)
    await hass.async_block_till_done()

    assert device_registry.async_get(device.id) is None
    assert entity_registry.async_get(STATUS) is None

    # Dropped from the data with the next refresh and stays removed while offline.
    await _refresh(hass, init_integration)
    assert JDOWNLOADER_ID not in init_integration.runtime_data.coordinator.data.devices
    assert hass.states.get(STATUS) is None

    # Comes back with new entities once MyJDownloader lists it again.
    mock_myjdapi.list_devices.return_value = device_list
    await _refresh(hass, init_integration)
    assert hass.states.get(STATUS).state == "running"
    # The entities of the removed device must not see data without it.
    assert "Unexpected error" not in caplog.text
