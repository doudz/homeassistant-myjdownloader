"""Tests for the MyJDownloader binary sensor platform."""

from unittest.mock import MagicMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant


async def test_connected_on_after_setup(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Test connected binary sensor is on after setup."""
    # init_integration is in signature to set up the integration.

    connected_state = hass.states.get("binary_sensor.jdownloader_mypc_connected")
    assert connected_state is not None
    assert connected_state.state == STATE_ON


async def test_connected_off_when_offline(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_myjdapi: MagicMock,
) -> None:
    """Test connected binary sensor goes off (not unavailable) when device is offline."""
    entry = init_integration

    mock_myjdapi.list_devices.return_value = []

    coordinator = entry.runtime_data.coordinator
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    connected_state = hass.states.get("binary_sensor.jdownloader_mypc_connected")
    assert connected_state is not None
    assert connected_state.state == STATE_OFF

    # The status sensor should be unavailable for contrast.
    status_state = hass.states.get("sensor.jdownloader_mypc_status")
    assert status_state is not None
    assert status_state.state == STATE_UNAVAILABLE
