"""Tests for the MyJDownloader switch platform."""

from unittest.mock import MagicMock

from myjdapi import MYJDConnectionException
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError


async def test_pause_switch_state_follows_status(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_device: MagicMock,
) -> None:
    """Test pause switch is off for RUNNING and on for PAUSE."""
    entry = init_integration

    # Default state is RUNNING, so pause switch should be off.
    pause_state = hass.states.get("switch.jdownloader_mypc_pause")
    assert pause_state is not None
    assert pause_state.state == STATE_OFF

    # Change to PAUSE and refresh.
    mock_device.downloadcontroller.get_current_state.return_value = "PAUSE"

    coordinator = entry.runtime_data.coordinator
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    pause_state = hass.states.get("switch.jdownloader_mypc_pause")
    assert pause_state is not None
    assert pause_state.state == STATE_ON


async def test_pause_switch_turn_on_off(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_device: MagicMock,
) -> None:
    """Test turning the pause switch on and off calls the correct methods."""
    # init_integration is in signature to set up the integration.

    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": "switch.jdownloader_mypc_pause"},
        blocking=True,
    )
    mock_device.downloadcontroller.pause_downloads.assert_called_with(True)

    mock_device.downloadcontroller.reset_mock()

    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": "switch.jdownloader_mypc_pause"},
        blocking=True,
    )
    mock_device.downloadcontroller.pause_downloads.assert_called_with(False)


async def test_limit_switch_turn_on_off(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_device: MagicMock,
) -> None:
    """Test the limit switch calls toolbar methods and follows get_status."""
    # init_integration is in signature to set up the integration.

    # Default: limit is False, so state should be off.
    limit_state = hass.states.get("switch.jdownloader_mypc_limit")
    assert limit_state is not None
    assert limit_state.state == STATE_OFF

    # Turn on the limit switch.
    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": "switch.jdownloader_mypc_limit"},
        blocking=True,
    )
    mock_device.toolbar.enable_downloadSpeedLimit.assert_called_once()

    # Simulate limit being enabled and refresh.
    mock_device.toolbar.get_status.return_value = {"limit": True}

    coordinator = init_integration.runtime_data.coordinator
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    limit_state = hass.states.get("switch.jdownloader_mypc_limit")
    assert limit_state is not None
    assert limit_state.state == STATE_ON

    # Turn off the limit switch.
    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": "switch.jdownloader_mypc_limit"},
        blocking=True,
    )
    mock_device.toolbar.disable_downloadSpeedLimit.assert_called_once()


async def test_switch_action_error_raises_homeassistanterror(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_device: MagicMock,
) -> None:
    """Test that a device action error raises HomeAssistantError."""
    # init_integration is in signature to set up the integration.

    mock_device.downloadcontroller.pause_downloads.side_effect = (
        MYJDConnectionException("offline")
    )

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": "switch.jdownloader_mypc_pause"},
            blocking=True,
        )
