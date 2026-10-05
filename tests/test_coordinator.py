"""Tests for the MyJDownloader coordinators and client."""

import logging
from unittest.mock import MagicMock

from myjdapi import (
    MYJDAuthFailedException,
    MYJDConnectionException,
    MYJDOfflineException,
    MYJDTokenInvalidException,
)
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
import requests

from custom_components.myjdownloader.const import DOMAIN, LATEST_VERSION_URL
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .conftest import _mock_device

STATUS = "sensor.jdownloader_mypc_status"
SECOND_DEVICE = {
    "name": "Laptop",
    "id": "0123456789abcdef0123456789abcdef",
    "type": "jd",
}


async def _refresh(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()


async def test_session_renewed_on_token_invalid(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_myjdapi: MagicMock
) -> None:
    """Test an expired session is renewed with reconnect and the call retried."""
    mock_myjdapi.update_devices.side_effect = [
        MYJDTokenInvalidException("MYJD"),
        None,
    ]
    await _refresh(hass, init_integration)

    mock_myjdapi.reconnect.assert_called_once()
    assert hass.states.get(STATUS).state == "running"


async def test_session_reconnect_falls_back_to_login(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_myjdapi: MagicMock
) -> None:
    """Test a failed reconnect logs in again."""
    mock_myjdapi.update_devices.side_effect = [
        MYJDTokenInvalidException("MYJD"),
        None,
    ]
    mock_myjdapi.reconnect.side_effect = requests.ConnectionError("reset")
    mock_myjdapi.connect.reset_mock()

    await _refresh(hass, init_integration)

    mock_myjdapi.connect.assert_called_once()
    assert hass.states.get(STATUS).state == "running"


@pytest.mark.parametrize(
    "exception",
    [
        requests.ConnectionError("unreachable"),
        requests.Timeout("timeout"),
        MYJDConnectionException("no connection"),
    ],
)
@pytest.mark.expected_errors("Error fetching myjdownloader data")
async def test_account_error_marks_unavailable_and_recovers(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_myjdapi: MagicMock,
    exception: Exception,
) -> None:
    """Test errors listing devices make entities unavailable until recovery."""
    mock_myjdapi.update_devices.side_effect = exception
    await _refresh(hass, init_integration)
    assert hass.states.get(STATUS).state == STATE_UNAVAILABLE
    assert not init_integration.runtime_data.coordinator.last_update_success

    mock_myjdapi.update_devices.side_effect = None
    await _refresh(hass, init_integration)
    assert hass.states.get(STATUS).state == "running"


def _reauth_flows(hass: HomeAssistant, entry: MockConfigEntry) -> list:
    return [
        flow
        for flow in hass.config_entries.flow.async_progress()
        if flow["context"].get("entry_id") == entry.entry_id
    ]


@pytest.mark.expected_errors("Authentication failed while fetching")
async def test_auth_error_during_refresh(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_myjdapi: MagicMock
) -> None:
    """Test a rejected session and a rejected login start a reauth."""
    mock_myjdapi.update_devices.side_effect = MYJDAuthFailedException("MYJD")
    mock_myjdapi.connect.side_effect = MYJDAuthFailedException("MYJD")
    await _refresh(hass, init_integration)
    assert not init_integration.runtime_data.coordinator.last_update_success
    assert hass.states.get(STATUS).state == STATE_UNAVAILABLE
    assert len(_reauth_flows(hass, init_integration)) == 1


async def test_rejected_session_logs_in_again(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_myjdapi: MagicMock
) -> None:
    """Test AUTH_FAILED for a session request leads to a new login, not a reauth.

    MyJDownloader answers AUTH_FAILED instead of TOKEN_INVALID for some
    sessions it dropped, for example after hours or after the computer slept.
    """
    mock_myjdapi.update_devices.side_effect = [MYJDAuthFailedException("MYJD"), None]
    mock_myjdapi.connect.reset_mock()
    await _refresh(hass, init_integration)
    mock_myjdapi.connect.assert_called_once()
    assert init_integration.runtime_data.coordinator.last_update_success
    assert hass.states.get(STATUS).state == "running"
    assert not _reauth_flows(hass, init_integration)


@pytest.mark.expected_errors("Error fetching myjdownloader data")
async def test_rejected_after_login_is_no_auth_error(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_myjdapi: MagicMock
) -> None:
    """Test AUTH_FAILED right after a successful login doesn't start a reauth."""
    mock_myjdapi.update_devices.side_effect = MYJDAuthFailedException("MYJD")
    await _refresh(hass, init_integration)
    assert not init_integration.runtime_data.coordinator.last_update_success
    assert not _reauth_flows(hass, init_integration)


@pytest.mark.parametrize(
    "exception",
    [
        MYJDConnectionException("no connection"),
        MYJDOfflineException("DEVICE"),
        # myjdapi bug when a direct connection disappears
        ValueError("list.remove(x): x not in list"),
    ],
)
async def test_device_error_only_affects_that_device(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_myjdapi: MagicMock,
    mock_devices: dict[str, MagicMock],
    mock_device: MagicMock,
    mock_latest_version: None,
    exception: Exception,
) -> None:
    """Test a failing JDownloader does not make the other one unavailable."""
    mock_devices[SECOND_DEVICE["id"]] = _mock_device(SECOND_DEVICE)
    mock_myjdapi.list_devices.return_value = [
        *mock_myjdapi.list_devices.return_value,
        SECOND_DEVICE,
    ]
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    mock_device.downloadcontroller.get_current_state.side_effect = exception
    await _refresh(hass, mock_config_entry)

    assert hass.states.get(STATUS).state == STATE_UNAVAILABLE
    assert hass.states.get("sensor.jdownloader_laptop_status").state == "running"
    # Listed by MyJDownloader, so still connected.
    assert hass.states.get("binary_sensor.jdownloader_mypc_connected").state == STATE_ON


async def test_offline_device_object_is_recreated(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_myjdapi: MagicMock,
    mock_device: MagicMock,
) -> None:
    """Test the cached Jddevice is dropped when the device reports offline."""
    assert mock_myjdapi.get_device.call_count == 1
    mock_device.downloadcontroller.get_current_state.side_effect = MYJDOfflineException(
        "DEVICE"
    )
    await _refresh(hass, init_integration)
    mock_device.downloadcontroller.get_current_state.side_effect = None
    await _refresh(hass, init_integration)

    assert mock_myjdapi.get_device.call_count == 2
    assert hass.states.get(STATUS).state == "running"


async def test_known_offline_device_restored_at_startup(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_myjdapi: MagicMock,
    mock_latest_version: None,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test a JDownloader known from the registry gets entities while offline."""
    mock_config_entry.add_to_hass(hass)
    device_registry.async_get_or_create(
        config_entry_id=mock_config_entry.entry_id,
        identifiers={(DOMAIN, "af9d03a21ddb917492dc1af8a6427f11")},
        name="JDownloader MyPC",
        model="jd",
    )
    mock_myjdapi.list_devices.return_value = []

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(STATUS).state == STATE_UNAVAILABLE
    assert (
        hass.states.get("binary_sensor.jdownloader_mypc_connected").state == STATE_OFF
    )


async def test_new_device_added_dynamically(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_myjdapi: MagicMock,
    mock_devices: dict[str, MagicMock],
) -> None:
    """Test a JDownloader coming online later gets entities without a reload."""
    assert hass.states.get("sensor.jdownloader_laptop_status") is None
    mock_devices[SECOND_DEVICE["id"]] = _mock_device(SECOND_DEVICE)
    mock_myjdapi.list_devices.return_value = [
        *mock_myjdapi.list_devices.return_value,
        SECOND_DEVICE,
    ]
    await _refresh(hass, init_integration)

    assert hass.states.get("sensor.jdownloader_laptop_status").state == "running"


async def test_availability_logged_once(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_myjdapi: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test becoming unavailable and available again is logged once each."""
    caplog.set_level(logging.INFO)
    mock_myjdapi.list_devices.return_value = []
    await _refresh(hass, init_integration)
    await _refresh(hass, init_integration)
    assert caplog.text.count("JDownloader MyPC is unavailable") == 1

    mock_myjdapi.list_devices.return_value = [
        {"name": "MyPC", "id": "af9d03a21ddb917492dc1af8a6427f11", "type": "jd"}
    ]
    await _refresh(hass, init_integration)
    await _refresh(hass, init_integration)
    assert caplog.text.count("JDownloader MyPC is available again") == 1


@pytest.mark.expected_errors("Error fetching myjdownloader_latest_version data")
async def test_latest_version_failure_does_not_block_setup(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_myjdapi: MagicMock,
    mock_device: MagicMock,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Test the update entity works without the build page."""
    aioclient_mock.get(LATEST_VERSION_URL, status=500)
    mock_device.update.is_update_available.return_value = True
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("update.jdownloader_mypc_update")
    assert state.state == STATE_ON
    assert state.attributes["latest_version"] == "48000+"
