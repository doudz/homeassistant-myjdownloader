"""Tests for the MyJDownloader entity services (until the Phase D rework)."""

from unittest.mock import MagicMock

from myjdapi import MYJDConnectionException
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.myjdownloader.const import DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

STATUS = "sensor.jdownloader_mypc_status"

pytestmark = pytest.mark.usefixtures("init_integration")


@pytest.mark.parametrize(
    ("service", "method"),
    [
        ("start_downloads", "downloadcontroller.start_downloads"),
        ("stop_downloads", "downloadcontroller.stop_downloads"),
        ("run_update_check", "update.run_update_check"),
        ("restart_and_update", "update.restart_and_update"),
    ],
)
async def test_device_services(
    hass: HomeAssistant, mock_device: MagicMock, service: str, method: str
) -> None:
    """Test the parameterless services call the JDownloader once."""
    await hass.services.async_call(
        DOMAIN, service, {"entity_id": STATUS}, blocking=True
    )
    group, name = method.split(".")
    getattr(getattr(mock_device, group), name).assert_called_once_with()


async def test_add_links(hass: HomeAssistant, mock_device: MagicMock) -> None:
    """Test links are sent newline separated with all options."""
    await hass.services.async_call(
        DOMAIN,
        "add_links",
        {
            "entity_id": STATUS,
            "links": ["https://example.com/a.zip", "https://example.com/b.zip"],
            "priority": "high",
            "autostart": True,
            "package_name": "Package",
        },
        blocking=True,
    )
    mock_device.linkgrabber.add_links.assert_called_once_with(
        [
            {
                "autoExtract": False,
                "autostart": True,
                "destinationFolder": None,
                "downloadPassword": None,
                "extractPassword": None,
                "links": "https://example.com/a.zip\nhttps://example.com/b.zip",
                "overwritePackagizerRules": False,
                "packageName": "Package",
                "priority": "HIGH",
            }
        ]
    )


async def test_service_error(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_device: MagicMock
) -> None:
    """Test API errors raise a translated HomeAssistantError."""
    mock_device.downloadcontroller.start_downloads.side_effect = (
        MYJDConnectionException("offline")
    )
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            DOMAIN, "start_downloads", {"entity_id": STATUS}, blocking=True
        )
    assert err.value.translation_key == "action_failed"
