"""Common fixtures for the MyJDownloader tests."""

from collections.abc import Generator
import json
import logging
from pathlib import Path
import re
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.syrupy import HomeAssistantSnapshotExtension
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from syrupy.assertion import SnapshotAssertion

from custom_components.myjdownloader.const import DOMAIN, LATEST_VERSION_URL
from homeassistant import block_async_io
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
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Return the snapshot fixture with the Home Assistant extension.

    Both syrupy and pytest-homeassistant-custom-component define a snapshot
    fixture; which plugin wins depends on the install order. A conftest fixture
    always wins, so snapshots are always stored in tests/snapshots.
    """
    return snapshot.use_extension(HomeAssistantSnapshotExtension)


@pytest.fixture(autouse=True, scope="session")
def detect_blocking_calls() -> Generator[None]:
    """Detect blocking I/O in the event loop like a running Home Assistant.

    Home Assistant enables this in its bootstrap, which tests do not run. For
    custom integrations it logs "Detected blocking call"; log_guard fails on it.
    The detection is bound to the main thread, so it is disabled again after
    the last test; otherwise it reports pytest-cov combining its data files.
    """
    calls = block_async_io._BLOCKED_CALLS.calls  # noqa: SLF001
    if calls:
        yield
        return
    block_async_io.enable()
    yield
    for call in calls:
        setattr(call.object, call.function, call.original_func)
    calls.clear()


# Credentials must never be logged: the test account and the token parameters
# of MyJDownloader URLs (unless masked).
_SECRETS = re.compile(
    rf"{re.escape(TEST_EMAIL)}|{re.escape(TEST_PASSWORD)}"
    r"|(email|sessiontoken|regaintoken|signature)=(?!\*\*REDACTED\*\*)[^&\s]",
    re.IGNORECASE,
)
# Always a bug, at any level. (Home Assistant logs tracebacks of handled errors
# at DEBUG, so tracebacks only count at ERROR level.)
_UNEXPECTED = ("Unexpected error", "Detected blocking call")


@pytest.fixture(autouse=True)
def log_guard(
    request: pytest.FixtureRequest, caplog: pytest.LogCaptureFixture
) -> Generator[None]:
    """Fail tests that log errors or credentials.

    Tests provoking errors on purpose declare them with
    @pytest.mark.expected_errors("substring", ...). Credentials are never allowed.
    """
    caplog.set_level(logging.DEBUG, logger="custom_components.myjdownloader")
    caplog.set_level(logging.DEBUG, logger="myjdapi")
    yield
    marker = request.node.get_closest_marker("expected_errors")
    allowed = marker.args if marker else ()
    formatter = logging.Formatter("%(levelname)s %(name)s: %(message)s")
    problems = []
    for record in caplog.get_records("setup") + caplog.get_records("call"):
        text = formatter.format(record)
        if _SECRETS.search(text):
            problems.append(f"credential logged: {text[:300]}")
        elif (
            record.levelno >= logging.ERROR or any(u in text for u in _UNEXPECTED)
        ) and not any(a in text for a in allowed):
            problems.append(f"unexpected log: {text[:300]}")
    if problems:
        pytest.fail("\n".join(problems), pytrace=False)


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a MyJDownloader config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="MyJDownloader",
        data={CONF_EMAIL: TEST_EMAIL, CONF_PASSWORD: TEST_PASSWORD},
        unique_id=TEST_EMAIL,
        version=2,
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
    device.toolbar.get_status.return_value = {"limit": False}
    device.update.is_update_available.return_value = False
    device.jd.get_core_revision.return_value = 48000
    return device


@pytest.fixture
def mock_devices() -> dict[str, MagicMock]:
    """Return the mocked Jddevice objects by device id."""
    return {
        info["id"]: _mock_device(info)
        for info in load_json_fixture("list_devices.json")
    }


@pytest.fixture
def mock_device(mock_devices: dict[str, MagicMock]) -> MagicMock:
    """Return the mocked Jddevice of the single test JDownloader ("MyPC")."""
    return next(iter(mock_devices.values()))


@pytest.fixture
def mock_myjdapi(mock_devices: dict[str, MagicMock]) -> Generator[MagicMock]:
    """Patch the myjdapi client used by the integration and its config flow."""
    devices = load_json_fixture("list_devices.json")
    with patch(
        "custom_components.myjdownloader.api.Myjdapi", autospec=True
    ) as mock_class:
        client = mock_class.return_value
        client.is_connected.return_value = True
        client.list_devices.return_value = devices
        client.get_device.side_effect = lambda device_name=None, device_id=None: (
            mock_devices[device_id]
        )
        yield client


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Prevent the config flow tests from setting up the created entry."""
    with (
        patch(
            "custom_components.myjdownloader.async_setup_entry", return_value=True
        ) as mock,
        patch("custom_components.myjdownloader.async_unload_entry", return_value=True),
    ):
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
