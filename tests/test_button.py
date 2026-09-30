"""Tests for the MyJDownloader button platform."""

from unittest.mock import MagicMock

from myjdapi import MYJDConnectionException
import pytest

from custom_components.myjdownloader.const import DOMAIN
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er

JDOWNLOADER_ID = "af9d03a21ddb917492dc1af8a6427f11"


def _get_jd_device_id(device_registry: dr.DeviceRegistry, entry_id: str) -> str:
    """Return the HA device id of the test JDownloader."""
    device = next(
        d
        for d in dr.async_entries_for_config_entry(device_registry, entry_id)
        if (DOMAIN, JDOWNLOADER_ID) in d.identifiers
    )
    return device.id


pytestmark = pytest.mark.usefixtures("init_integration")


@pytest.mark.parametrize(
    ("entity_id", "method"),
    [
        (
            "button.jdownloader_mypc_start_downloads",
            "downloadcontroller.start_downloads",
        ),
        ("button.jdownloader_mypc_stop_downloads", "downloadcontroller.stop_downloads"),
        ("button.jdownloader_mypc_run_update_check", "update.run_update_check"),
    ],
)
async def test_button_press(
    hass: HomeAssistant, mock_device: MagicMock, entity_id: str, method: str
) -> None:
    """Test pressing a button calls the corresponding JDownloader method once."""
    await hass.services.async_call(
        "button", "press", {"entity_id": entity_id}, blocking=True
    )
    group, name = method.split(".")
    getattr(getattr(mock_device, group), name).assert_called_once_with()


async def test_run_update_check_entity_category(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    """Test the run_update_check button has CONFIG entity category."""
    entry = entity_registry.async_get("button.jdownloader_mypc_run_update_check")
    assert entry is not None
    assert entry.entity_category == EntityCategory.CONFIG


async def test_button_press_failure(
    hass: HomeAssistant, mock_device: MagicMock
) -> None:
    """Test a failing button press raises a translated HomeAssistantError."""
    mock_device.downloadcontroller.start_downloads.side_effect = (
        MYJDConnectionException("offline")
    )
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            "button",
            "press",
            {"entity_id": "button.jdownloader_mypc_start_downloads"},
            blocking=True,
        )
    assert err.value.translation_key == "action_failed"
