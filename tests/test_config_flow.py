"""Tests for the MyJDownloader config flow."""

from unittest.mock import MagicMock

from myjdapi import (
    MYJDAuthFailedException,
    MYJDConnectionException,
    MYJDEmailInvalidException,
    MYJDErrorEmailNotConfirmedException,
)
import pytest
import requests

from custom_components.myjdownloader.const import DOMAIN
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_USER
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError

from .conftest import TEST_EMAIL, TEST_PASSWORD

USER_INPUT = {CONF_EMAIL: TEST_EMAIL, CONF_PASSWORD: TEST_PASSWORD}

ERRORS = [
    (MYJDConnectionException("offline"), "cannot_connect"),
    (requests.ConnectionError("unreachable"), "cannot_connect"),
    (MYJDAuthFailedException("MYJD"), "invalid_auth"),
    (MYJDErrorEmailNotConfirmedException("MYJD"), "invalid_auth"),
    (MYJDEmailInvalidException("MYJD"), "invalid_auth"),
    (RuntimeError("boom"), "unknown"),
]


@pytest.mark.usefixtures("mock_setup_entry")
async def test_user_flow(hass: HomeAssistant, mock_myjdapi: MagicMock) -> None:
    """Test the full user flow with stripped email and case-preserved title."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: " Test@Example.com ", CONF_PASSWORD: TEST_PASSWORD},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Test@Example.com"
    assert result["data"] == {
        CONF_EMAIL: "Test@Example.com",
        CONF_PASSWORD: TEST_PASSWORD,
    }
    assert result["result"].unique_id == "test@example.com"
    mock_myjdapi.connect.assert_called_once_with("Test@Example.com", TEST_PASSWORD)
    mock_myjdapi.disconnect.assert_called_once()


@pytest.mark.usefixtures("mock_setup_entry")
@pytest.mark.parametrize(("side_effect", "error"), ERRORS)
@pytest.mark.expected_errors("Unexpected exception")
async def test_user_flow_errors(
    hass: HomeAssistant,
    mock_myjdapi: MagicMock,
    side_effect: Exception,
    error: str,
) -> None:
    """Test errors in the user flow and recovery to CREATE_ENTRY."""
    mock_myjdapi.connect.side_effect = side_effect
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    mock_myjdapi.connect.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.usefixtures("mock_setup_entry")
async def test_user_flow_already_configured(
    hass: HomeAssistant,
    mock_myjdapi: MagicMock,
    mock_config_entry: MagicMock,
) -> None:
    """Test abort when the account is already configured."""
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: "TEST@example.com", CONF_PASSWORD: TEST_PASSWORD},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    mock_myjdapi.connect.assert_not_called()


@pytest.mark.usefixtures("mock_setup_entry")
async def test_reauth_flow(
    hass: HomeAssistant,
    mock_myjdapi: MagicMock,
    mock_config_entry: MagicMock,
) -> None:
    """Test the reauth flow updates only the password."""
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["description_placeholders"]["email"] == TEST_EMAIL

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new-password"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data[CONF_PASSWORD] == "new-password"
    assert mock_config_entry.data[CONF_EMAIL] == TEST_EMAIL


@pytest.mark.usefixtures("mock_setup_entry")
@pytest.mark.parametrize(("side_effect", "error"), ERRORS)
@pytest.mark.expected_errors("Unexpected exception")
async def test_reauth_flow_errors(
    hass: HomeAssistant,
    mock_myjdapi: MagicMock,
    mock_config_entry: MagicMock,
    side_effect: Exception,
    error: str,
) -> None:
    """Test errors in the reauth flow and recovery to reauth_successful."""
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reauth_flow(hass)

    mock_myjdapi.connect.side_effect = side_effect
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new-password"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    mock_myjdapi.connect.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new-password"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"


@pytest.mark.usefixtures("mock_setup_entry")
async def test_reconfigure_flow(
    hass: HomeAssistant,
    mock_myjdapi: MagicMock,
    mock_config_entry: MagicMock,
) -> None:
    """Test the reconfigure flow updates credentials."""
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: "test@example.com", CONF_PASSWORD: "new-password"},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data[CONF_PASSWORD] == "new-password"


@pytest.mark.usefixtures("mock_setup_entry")
@pytest.mark.parametrize(("side_effect", "error"), ERRORS)
@pytest.mark.expected_errors("Unexpected exception")
async def test_reconfigure_flow_errors(
    hass: HomeAssistant,
    mock_myjdapi: MagicMock,
    mock_config_entry: MagicMock,
    side_effect: Exception,
    error: str,
) -> None:
    """Test errors in the reconfigure flow and recovery to reconfigure_successful."""
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reconfigure_flow(hass)

    mock_myjdapi.connect.side_effect = side_effect
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: "test@example.com", CONF_PASSWORD: "new-password"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    mock_myjdapi.connect.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: "test@example.com", CONF_PASSWORD: "new-password"},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"


@pytest.mark.usefixtures("mock_setup_entry")
async def test_reconfigure_wrong_account(
    hass: HomeAssistant,
    mock_myjdapi: MagicMock,
    mock_config_entry: MagicMock,
) -> None:
    """Test reconfigure aborts when the email belongs to a different account."""
    mock_config_entry.add_to_hass(hass)
    result = await mock_config_entry.start_reconfigure_flow(hass)

    original_data = dict(mock_config_entry.data)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_EMAIL: "other@example.com", CONF_PASSWORD: "x"},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_account"
    assert mock_config_entry.data == original_data
    mock_myjdapi.connect.assert_not_called()


async def test_setup_auth_failed_starts_reauth(
    hass: HomeAssistant,
    mock_myjdapi: MagicMock,
    mock_config_entry: MagicMock,
) -> None:
    """Test that a failed auth during setup starts a reauth flow."""
    mock_myjdapi.connect.side_effect = MYJDAuthFailedException("MYJD")
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress()
    assert len(flows) == 1
    assert flows[0]["step_id"] == "reauth_confirm"
    assert flows[0]["context"]["source"] == SOURCE_REAUTH
    assert flows[0]["context"]["entry_id"] == mock_config_entry.entry_id


async def test_action_auth_error_starts_reauth(
    hass: HomeAssistant,
    init_integration: MagicMock,
    mock_device: MagicMock,
    mock_myjdapi: MagicMock,
) -> None:
    """Test that an auth error during a device action starts a reauth flow."""
    mock_device.downloadcontroller.pause_downloads.side_effect = (
        MYJDAuthFailedException("MYJD")
    )

    with pytest.raises(HomeAssistantError) as exc_info:
        await hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": "switch.jdownloader_mypc_pause"},
            blocking=True,
        )

    assert exc_info.value.translation_key == "auth_failed"

    await hass.async_block_till_done()

    flows = hass.config_entries.flow.async_progress()
    entry_flows = [
        f for f in flows if f["context"].get("entry_id") == init_integration.entry_id
    ]
    assert len(entry_flows) == 1
    assert entry_flows[0]["step_id"] == "reauth_confirm"
    assert entry_flows[0]["context"]["source"] == SOURCE_REAUTH
    assert entry_flows[0]["context"]["entry_id"] == init_integration.entry_id
