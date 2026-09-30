"""Fault injection tests for the MyJDownloader integration."""

from datetime import timedelta
from unittest.mock import MagicMock

from freezegun.api import FrozenDateTimeFactory
from myjdapi import (
    MYJDConnectionException,
    MYJDDecodeException,
    MYJDMaintenanceException,
    MYJDOverloadException,
    MYJDSessionException,
    MYJDTokenInvalidException,
    MYJDTooManyRequestsException,
)
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
import requests

from homeassistant.const import STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError


async def _refresh(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()


# --------------------------------------------------------------------------- #
# Shared exception list                                                        #
# --------------------------------------------------------------------------- #

ACCOUNT_EXCEPTIONS = [
    requests.Timeout("t"),
    requests.ConnectionError("c"),
    MYJDConnectionException("c"),
    MYJDMaintenanceException("MYJD"),
    MYJDOverloadException("MYJD"),
    MYJDTooManyRequestsException("MYJD"),
    MYJDDecodeException("d"),
    ValueError("list.remove(x): x not in list"),
]

# A rate limit hit by a device request pauses the whole account (see
# test_device_rate_limit_backs_off_account); all other errors stay scoped.
DEVICE_EXCEPTIONS = [
    exc
    for exc in ACCOUNT_EXCEPTIONS
    if not isinstance(exc, MYJDTooManyRequestsException)
]
BACKOFF_TYPES = (
    MYJDMaintenanceException,
    MYJDOverloadException,
    MYJDTooManyRequestsException,
)

DEVICE_CALL_NAMES = [
    "get_current_state",
    "get_speed_in_bytes",
    "get_status",
    "is_update_available",
    "get_core_revision",
]


# --------------------------------------------------------------------------- #
# Account-level call faults                                                    #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("exception", ACCOUNT_EXCEPTIONS)
@pytest.mark.expected_errors("Error fetching myjdownloader data")
async def test_account_call_fault(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_myjdapi: MagicMock,
    exception: Exception,
) -> None:
    """Test account-level errors make entities unavailable until recovery."""
    mock_myjdapi.update_devices.side_effect = exception
    await _refresh(hass, init_integration)

    assert hass.states.get("sensor.jdownloader_mypc_status").state == STATE_UNAVAILABLE
    assert (
        hass.states.get("binary_sensor.jdownloader_mypc_connected").state
        == STATE_UNAVAILABLE
    )
    assert not init_integration.runtime_data.coordinator.last_update_success

    mock_myjdapi.update_devices.side_effect = None
    await _refresh(hass, init_integration)

    assert hass.states.get("sensor.jdownloader_mypc_status").state == "running"
    assert hass.states.get("binary_sensor.jdownloader_mypc_connected").state == STATE_ON


# --------------------------------------------------------------------------- #
# Device-level call faults                                                     #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("exception", DEVICE_EXCEPTIONS)
@pytest.mark.parametrize("call_name", DEVICE_CALL_NAMES)
async def test_device_call_fault(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_device: MagicMock,
    mock_myjdapi: MagicMock,
    exception: Exception,
    call_name: str,
) -> None:
    """Test a failing device call only affects that JDownloader."""
    entry = init_integration

    # Resolve the callable on the mock to inject the side effect.
    if call_name == "get_current_state":
        target = mock_device.downloadcontroller.get_current_state
    elif call_name == "get_speed_in_bytes":
        target = mock_device.downloadcontroller.get_speed_in_bytes
    elif call_name == "get_status":
        target = mock_device.toolbar.get_status
    elif call_name == "is_update_available":
        target = mock_device.update.is_update_available
    else:  # get_core_revision
        target = mock_device.jd.get_core_revision
        # Force a new query by making update_available True.
        mock_device.update.is_update_available.return_value = True

    target.side_effect = exception
    await _refresh(hass, entry)

    # Status sensor unavailable (device data incomplete).
    assert hass.states.get("sensor.jdownloader_mypc_status").state == STATE_UNAVAILABLE
    # Binary sensor still on (account-level device list is fine).
    assert hass.states.get("binary_sensor.jdownloader_mypc_connected").state == STATE_ON
    # Coordinator still reports success (only this device failed, not the account).
    assert entry.runtime_data.coordinator.last_update_success

    # Restore and recover.
    target.side_effect = None
    if call_name == "get_core_revision":
        mock_device.update.is_update_available.return_value = False

    await _refresh(hass, entry)
    assert hass.states.get("sensor.jdownloader_mypc_status").state == "running"


# --------------------------------------------------------------------------- #
# Session errors recover via reconnect                                         #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "exception",
    [MYJDTokenInvalidException("MYJD"), MYJDSessionException("MYJD")],
)
async def test_session_errors_recover(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_myjdapi: MagicMock,
    exception: Exception,
) -> None:
    """Test session exceptions trigger reconnect and then succeed."""
    mock_myjdapi.update_devices.side_effect = [exception, None]
    await _refresh(hass, init_integration)

    mock_myjdapi.reconnect.assert_called_once()
    assert hass.states.get("sensor.jdownloader_mypc_status").state == "running"


# --------------------------------------------------------------------------- #
# Session renewal fails, falls back to login                                   #
# --------------------------------------------------------------------------- #


async def test_session_renewal_fails_then_login(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_myjdapi: MagicMock,
) -> None:
    """Test a failed reconnect falls back to connect (fresh login)."""
    mock_myjdapi.update_devices.side_effect = [
        MYJDTokenInvalidException("MYJD"),
        None,
    ]
    mock_myjdapi.reconnect.side_effect = MYJDTokenInvalidException("MYJD")
    mock_myjdapi.connect.reset_mock()

    await _refresh(hass, init_integration)

    mock_myjdapi.connect.assert_called_once()
    assert hass.states.get("sensor.jdownloader_mypc_status").state == "running"


# --------------------------------------------------------------------------- #
# Unexpected library error                                                     #
# --------------------------------------------------------------------------- #


@pytest.mark.expected_errors("Unexpected error fetching myjdownloader data")
async def test_unexpected_library_error(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_myjdapi: MagicMock,
) -> None:
    """Test an unexpected exception is logged and makes entities unavailable."""
    mock_myjdapi.update_devices.side_effect = RuntimeError("library bug")
    await _refresh(hass, init_integration)

    assert hass.states.get("sensor.jdownloader_mypc_status").state == STATE_UNAVAILABLE
    assert not init_integration.runtime_data.coordinator.last_update_success

    mock_myjdapi.update_devices.side_effect = None
    await _refresh(hass, init_integration)
    assert hass.states.get("sensor.jdownloader_mypc_status").state == "running"


# --------------------------------------------------------------------------- #
# Action faults raise HomeAssistantError                                       #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("exception", ACCOUNT_EXCEPTIONS)
async def test_action_faults(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_device: MagicMock,
    exception: Exception,
) -> None:
    """Test that device action errors surface as HomeAssistantError."""
    mock_device.downloadcontroller.pause_downloads.side_effect = exception

    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": "switch.jdownloader_mypc_pause"},
            blocking=True,
        )

    expected = (
        "rate_limited_action"
        if isinstance(exception, BACKOFF_TYPES)
        else "action_failed"
    )
    assert err.value.translation_key == expected


# --------------------------------------------------------------------------- #
# Backoff when MyJDownloader asks to slow down                                 #
# --------------------------------------------------------------------------- #


@pytest.mark.expected_errors("asks to slow down")
async def test_device_rate_limit_backs_off_account(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_device: MagicMock
) -> None:
    """Test a rate limit on a device request pauses the whole account."""
    mock_device.downloadcontroller.get_current_state.side_effect = (
        MYJDTooManyRequestsException("MYJD")
    )
    coordinator = init_integration.runtime_data.coordinator
    await _refresh(hass, init_integration)

    assert not coordinator.last_update_success
    assert coordinator.last_exception.retry_after == 120
    assert (
        hass.states.get("binary_sensor.jdownloader_mypc_connected").state
        == STATE_UNAVAILABLE
    )


@pytest.mark.expected_errors("asks to slow down")
async def test_backoff_grows_and_resets(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_myjdapi: MagicMock
) -> None:
    """Test the pauses double up to 30 minutes and start over after a success."""
    coordinator = init_integration.runtime_data.coordinator
    mock_myjdapi.update_devices.side_effect = MYJDTooManyRequestsException("MYJD")
    delays = []
    for _ in range(7):
        await _refresh(hass, init_integration)
        delays.append(coordinator.last_exception.retry_after)
    assert delays == [120, 240, 480, 960, 1800, 1800, 1800]

    mock_myjdapi.update_devices.side_effect = None
    await _refresh(hass, init_integration)
    assert coordinator.last_update_success
    assert hass.states.get("sensor.jdownloader_mypc_status").state == "running"

    mock_myjdapi.update_devices.side_effect = MYJDOverloadException("MYJD")
    await _refresh(hass, init_integration)
    assert coordinator.last_exception.retry_after == 120


@pytest.mark.expected_errors("asks to slow down")
async def test_backoff_delays_next_poll(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_myjdapi: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test no request is sent before the pause is over."""
    mock_myjdapi.update_devices.side_effect = MYJDTooManyRequestsException("MYJD")
    await _refresh(hass, init_integration)
    calls = mock_myjdapi.update_devices.call_count

    freezer.tick(timedelta(seconds=90))  # normal interval is 60 s
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_myjdapi.update_devices.call_count == calls

    freezer.tick(timedelta(seconds=40))  # 130 s > 120 s pause
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_myjdapi.update_devices.call_count == calls + 1
