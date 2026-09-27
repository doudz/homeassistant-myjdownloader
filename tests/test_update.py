"""Tests for the MyJDownloader update platform."""

from unittest.mock import MagicMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant


async def test_no_update_available(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
) -> None:
    """Test update entity state when no update is available."""
    # init_integration is in signature to set up the integration.

    update_state = hass.states.get("update.jdownloader_mypc_update")
    assert update_state is not None
    assert update_state.state == STATE_OFF
    assert update_state.attributes["installed_version"] == "48000"
    assert update_state.attributes["latest_version"] == "48000"


async def test_update_available(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_device: MagicMock,
) -> None:
    """Test update entity state when an update is available."""
    entry = init_integration

    mock_device.update.is_update_available.return_value = True

    coordinator = entry.runtime_data.coordinator
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    update_state = hass.states.get("update.jdownloader_mypc_update")
    assert update_state is not None
    assert update_state.state == STATE_ON
    assert update_state.attributes["installed_version"] == "48000"
    assert update_state.attributes["latest_version"] == "50639"


async def test_update_install(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_device: MagicMock,
) -> None:
    """Test calling the install service triggers restart_and_update."""
    entry = init_integration

    # Make an update available first so install makes sense.
    mock_device.update.is_update_available.return_value = True

    coordinator = entry.runtime_data.coordinator
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    await hass.services.async_call(
        "update",
        "install",
        {"entity_id": "update.jdownloader_mypc_update"},
        blocking=True,
    )

    mock_device.update.restart_and_update.assert_called_once()
