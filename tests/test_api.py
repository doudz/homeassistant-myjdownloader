"""Tests for the myjdapi client wrapper."""

import logging
from unittest.mock import MagicMock

from myjdapi import MYJDAuthFailedException
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
import requests

from homeassistant.core import HomeAssistant

from .conftest import TEST_EMAIL

SECRETS = ("tok-123", "regain-456", "sig-789", "dl-secret")

# Messages as built by myjdapi and requests: they contain the request URL and
# the request payload.
AUTH_MESSAGE = (
    "\n\tSOURCE: MYJD\n\tTYPE: AUTH_FAILED\n------\nREQUEST_URL: "
    f"https://api.jdownloader.org/my/connect?email={TEST_EMAIL}&appkey=x&rid=1"
    "&signature=sig-789\n"
)
CONNECTION_MESSAGE = (
    "HTTPSConnectionPool(host='api.jdownloader.org', port=443): Max retries "
    "exceeded with url: /my/listdevices?sessiontoken=tok-123&regaintoken=regain-456"
    "&rid=1&signature=sig-789 (Caused by NameResolutionError)"
)


def _assert_no_secrets(text: str) -> None:
    assert TEST_EMAIL not in text
    for secret in SECRETS:
        assert secret not in text


async def test_auth_error_scrubbed(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_myjdapi: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test email and signature of a failed login are not logged."""
    caplog.set_level(logging.DEBUG)
    error = MYJDAuthFailedException("MYJD", AUTH_MESSAGE + 'DATA:\n{"p": "dl-secret"}')
    mock_myjdapi.connect.side_effect = error
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    _assert_no_secrets(caplog.text)
    _assert_no_secrets(str(error))
    assert "email=**REDACTED**" in str(error)


async def test_connection_error_scrubbed(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_myjdapi: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test session tokens of a failed request are not logged."""
    caplog.set_level(logging.DEBUG)
    mock_myjdapi.update_devices.side_effect = requests.ConnectionError(
        CONNECTION_MESSAGE
    )
    coordinator = init_integration.runtime_data.coordinator
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert not coordinator.last_update_success
    chain = []
    error: BaseException | None = coordinator.last_exception
    while error is not None:
        chain.append(repr(error))
        error = error.__cause__
    assert len(chain) >= 2
    _assert_no_secrets(" ".join(chain))
    _assert_no_secrets(caplog.text)
