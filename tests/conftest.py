"""Common fixtures for the MyJDownloader tests."""

from collections.abc import Generator
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.myjdownloader.const import DOMAIN, LATEST_VERSION_URL
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant

FIXTURES = Path(__file__).parent / "fixtures"

TEST_EMAIL = "test@example.com"
TEST_PASSWORD = "test-password"


def load_json_fixture(name: str) -> Any:
    """Load a JSON fixture from the fixtures directory."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading custom integrations in all tests."""


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a MyJDownloader config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="MyJDownloader",
        data={CONF_EMAIL: TEST_EMAIL, CONF_PASSWORD: TEST_PASSWORD},
    )


def _mock_device(device_info: dict[str, str]) -> MagicMock:
    """Return a mocked myjdapi Jddevice with realistic return values."""
    device = MagicMock()
    device.name = device_info["name"]
    device.device_id = device_info["id"]
    device.device_type = device_info["type"]
    device.downloadcontroller.get_current_state.return_value = "RUNNING"
    device.downloadcontroller.get_speed_in_bytes.return_value = 2_500_000
    device.downloads.query_packages.return_value = [{"name": "package"}]
    device.downloads.query_links.return_value = [{"name": "link1"}, {"name": "link2"}]
    device.toolbar.status_downloadSpeedLimit.return_value = 0
    device.update.is_update_available.return_value = False
    device.jd.get_core_revision.return_value = 48000
    return device


@pytest.fixture
def mock_myjdapi() -> Generator[MagicMock]:
    """Patch the myjdapi client used by the integration and its config flow."""
    devices = load_json_fixture("list_devices.json")
    with patch("custom_components.myjdownloader.Myjdapi", autospec=True) as mock_class:
        client = mock_class.return_value
        client.is_connected.return_value = True
        client.list_devices.return_value = devices
        client.get_device.side_effect = lambda device_name=None, device_id=None: (
            _mock_device(next(d for d in devices if d["id"] == device_id))
        )
        yield client


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Prevent the config flow tests from setting up the created entry."""
    with patch(
        "custom_components.myjdownloader.async_setup_entry", return_value=True
    ) as mock:
        yield mock


@pytest.fixture
def mock_latest_version(aioclient_mock: AiohttpClientMocker) -> None:
    """Mock the JDownloader build page queried by the update entity."""
    aioclient_mock.get(
        LATEST_VERSION_URL, text=(FIXTURES / "build.php.html").read_text()
    )


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_myjdapi: MagicMock,
    mock_latest_version: None,
) -> MockConfigEntry:
    """Set up the integration and return its config entry."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_config_entry
