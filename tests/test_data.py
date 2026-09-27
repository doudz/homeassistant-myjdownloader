"""Unusual data tests for the MyJDownloader integration."""

from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.myjdownloader.const import DOMAIN
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .conftest import _mock_device


async def _refresh(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()


# --------------------------------------------------------------------------- #
# 1. No devices online                                                         #
# --------------------------------------------------------------------------- #


async def test_no_devices(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_myjdapi: MagicMock,
) -> None:
    """Test empty device list sets online count to 0 and status unavailable."""
    entry = init_integration
    mock_myjdapi.list_devices.return_value = []
    await _refresh(hass, entry)

    online_entries = [
        e
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        if e.unique_id.endswith("_online_count")
    ]
    assert len(online_entries) == 1
    assert hass.states.get(online_entries[0].entity_id).state == "0"
    assert hass.states.get("sensor.jdownloader_mypc_status").state == STATE_UNAVAILABLE


# --------------------------------------------------------------------------- #
# 2. list_devices returns None                                                 #
# --------------------------------------------------------------------------- #


async def test_list_devices_none(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_myjdapi: MagicMock,
) -> None:
    """Test None from list_devices is handled gracefully (no crash)."""
    entry = init_integration
    mock_myjdapi.list_devices.return_value = None
    await _refresh(hass, entry)

    online_entries = [
        e
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        if e.unique_id.endswith("_online_count")
    ]
    assert len(online_entries) == 1
    assert hass.states.get(online_entries[0].entity_id).state == "0"


# --------------------------------------------------------------------------- #
# 3. Various current_state values                                              #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("raw", "expected_status", "expected_pause"),
    [
        (None, STATE_UNKNOWN, STATE_UNKNOWN),
        ("", STATE_UNKNOWN, STATE_UNKNOWN),
        ("running", "running", STATE_OFF),
        ("pause", "paused", STATE_ON),
        ("SOMETHING_NEW", STATE_UNKNOWN, STATE_OFF),
    ],
)
async def test_current_state_values(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_device: MagicMock,
    raw: str | None,
    expected_status: str,
    expected_pause: str,
) -> None:
    """Test various raw download controller states."""
    entry = init_integration
    mock_device.downloadcontroller.get_current_state.return_value = raw

    await _refresh(hass, entry)

    assert hass.states.get("sensor.jdownloader_mypc_status").state == expected_status
    assert hass.states.get("switch.jdownloader_mypc_pause").state == expected_pause


# --------------------------------------------------------------------------- #
# 4. Various speed values                                                      #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, STATE_UNKNOWN),
        (0, "0.0"),
        (1_234_567, "1.23"),
        (10**12, "1000000.0"),
    ],
)
async def test_speed_values(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_device: MagicMock,
    raw: int | None,
    expected: str,
) -> None:
    """Test various download speed values."""
    entry = init_integration
    mock_device.downloadcontroller.get_speed_in_bytes.return_value = raw

    await _refresh(hass, entry)

    assert hass.states.get("sensor.jdownloader_mypc_download_speed").state == expected


# --------------------------------------------------------------------------- #
# 5. Various toolbar status values                                             #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, STATE_UNKNOWN),
        ({}, STATE_OFF),
        ({"limit": True}, STATE_ON),
    ],
)
async def test_toolbar_values(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_device: MagicMock,
    raw: dict | None,
    expected: str,
) -> None:
    """Test various toolbar get_status return values."""
    entry = init_integration
    mock_device.toolbar.get_status.return_value = raw

    await _refresh(hass, entry)

    assert hass.states.get("switch.jdownloader_mypc_limit").state == expected


# --------------------------------------------------------------------------- #
# 6. Core revision values                                                      #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("value", "expected_installed"),
    [
        (50639, "50639"),
        ("50639", "50639"),
        (None, None),
    ],
)
async def test_core_revision_values(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_myjdapi: MagicMock,
    mock_devices: dict[str, MagicMock],
    mock_latest_version: None,
    value: int | str | None,
    expected_installed: str | None,
) -> None:
    """Test various core revision return values from the action endpoint."""
    mock_device = mock_devices["af9d03a21ddb917492dc1af8a6427f11"]
    mock_device.action.side_effect = lambda path, *a, **k: (
        value if path == "/jd/getCoreRevision" else None
    )

    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    update_state = hass.states.get("update.jdownloader_mypc_update")
    assert update_state is not None

    if expected_installed is not None:
        assert update_state.attributes["installed_version"] == expected_installed
        # Update entity must not be "unavailable" when revision is valid.
        assert update_state.state != STATE_UNAVAILABLE
    else:
        assert update_state.attributes.get("installed_version") is None


# --------------------------------------------------------------------------- #
# 7. Many links                                                                #
# --------------------------------------------------------------------------- #


async def test_many_links(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_device: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test the links sensor handles a large number of entries."""
    entry = init_integration

    mock_device.downloads.query_links.return_value = [
        {"name": f"file{i}.zip", "bytesTotal": i} for i in range(5000)
    ]

    entity_registry.async_update_entity(
        "sensor.jdownloader_mypc_links", disabled_by=None
    )
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    links_state = hass.states.get("sensor.jdownloader_mypc_links")
    assert links_state is not None
    assert links_state.state == "5000"


# --------------------------------------------------------------------------- #
# 8. Unicode and duplicate device names                                        #
# --------------------------------------------------------------------------- #


async def test_unicode_and_duplicate_names(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_myjdapi: MagicMock,
    mock_devices: dict[str, MagicMock],
    mock_latest_version: None,
) -> None:
    """Test devices with unicode names and distinct ids both get entities."""
    second = {
        "name": "Ümläut \U0001f680 PC",
        "id": "0123456789abcdef0123456789abcdef",
        "type": "jd",
    }
    mock_devices[second["id"]] = _mock_device(second)
    mock_myjdapi.list_devices.return_value = [
        *mock_myjdapi.list_devices.return_value,
        second,
    ]

    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    entity_reg = er.async_get(hass)

    for device_id in ("af9d03a21ddb917492dc1af8a6427f11", second["id"]):
        unique_id = f"{device_id}_status"
        entity_id = entity_reg.async_get_entity_id("sensor", DOMAIN, unique_id)
        assert entity_id is not None, f"Missing status entity for {device_id}"
        assert hass.states.get(entity_id).state == "running"


async def test_duplicate_device_names(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_myjdapi: MagicMock,
    mock_devices: dict[str, MagicMock],
    mock_latest_version: None,
) -> None:
    """Test two devices sharing the same name get distinct entity_ids."""
    second = {
        "name": "MyPC",
        "id": "0123456789abcdef0123456789abcdef",
        "type": "jd",
    }
    mock_devices[second["id"]] = _mock_device(second)
    mock_myjdapi.list_devices.return_value = [
        *mock_myjdapi.list_devices.return_value,
        second,
    ]

    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    entity_reg = er.async_get(hass)

    entity_ids: list[str] = []
    for device_id in ("af9d03a21ddb917492dc1af8a6427f11", second["id"]):
        unique_id = f"{device_id}_status"
        entity_id = entity_reg.async_get_entity_id("sensor", DOMAIN, unique_id)
        assert entity_id is not None, f"Missing status entity for {device_id}"
        entity_ids.append(entity_id)
        assert hass.states.get(entity_id).state == "running"

    # The two entities must have different entity_ids despite the same name.
    assert len(set(entity_ids)) == 2
