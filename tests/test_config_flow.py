"""Tests for the MyJDownloader config flow."""

from unittest.mock import MagicMock

from myjdapi import MYJDAuthFailedException, MYJDConnectionException
import pytest
import requests

from custom_components.myjdownloader.const import DOMAIN
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import TEST_EMAIL, TEST_PASSWORD

USER_INPUT = {CONF_EMAIL: TEST_EMAIL, CONF_PASSWORD: TEST_PASSWORD}


pytestmark = pytest.mark.usefixtures("mock_setup_entry")


async def test_user_flow(hass: HomeAssistant, mock_myjdapi: MagicMock) -> None:
    """Test the full user flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "MyJDownloader"
    assert result["data"] == USER_INPUT
    mock_myjdapi.connect.assert_called_once_with(TEST_EMAIL, TEST_PASSWORD)


@pytest.mark.parametrize(
    ("side_effect", "error"),
    [
        (MYJDConnectionException("offline"), "cannot_connect"),
        (requests.ConnectionError("unreachable"), "cannot_connect"),
        (MYJDAuthFailedException("MYJD"), "invalid_auth"),
        (RuntimeError("boom"), "unknown"),
    ],
)
async def test_user_flow_errors(
    hass: HomeAssistant,
    mock_myjdapi: MagicMock,
    side_effect: Exception,
    error: str,
) -> None:
    """Test errors in the user flow and recovery afterwards."""
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
