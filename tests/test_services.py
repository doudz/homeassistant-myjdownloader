"""Tests for the MyJDownloader actions."""

from unittest.mock import MagicMock

from myjdapi import MYJDConnectionException
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
import voluptuous as vol

from custom_components.myjdownloader.const import DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr, issue_registry as ir

from .conftest import _mock_device

STATUS = "sensor.jdownloader_mypc_status"

JDOWNLOADER_ID = "af9d03a21ddb917492dc1af8a6427f11"


def _get_jd_device_id(device_registry: dr.DeviceRegistry, entry_id: str) -> str:
    """Return the HA device id of the test JDownloader."""
    device = next(
        d
        for d in dr.async_entries_for_config_entry(device_registry, entry_id)
        if (DOMAIN, JDOWNLOADER_ID) in d.identifiers
    )
    return device.id


def _get_account_device_id(device_registry: dr.DeviceRegistry, entry_id: str) -> str:
    """Return the HA device id of the account device."""
    device = next(
        d
        for d in dr.async_entries_for_config_entry(device_registry, entry_id)
        if (DOMAIN, f"account_{entry_id}") in d.identifiers
    )
    return device.id


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


async def test_add_links_device_id(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_device: MagicMock,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test add_links with device_id target and default priority."""
    jd_device_id = _get_jd_device_id(device_registry, init_integration.entry_id)
    await hass.services.async_call(
        DOMAIN,
        "add_links",
        {"device_id": jd_device_id, "links": ["https://example.com/a.zip"]},
        blocking=True,
    )
    mock_device.linkgrabber.add_links.assert_called_once_with(
        [
            {
                "autoExtract": False,
                "autostart": False,
                "destinationFolder": None,
                "downloadPassword": None,
                "extractPassword": None,
                "links": "https://example.com/a.zip",
                "overwritePackagizerRules": False,
                "packageName": None,
                "priority": "DEFAULT",
            }
        ]
    )


async def test_targets_deduplicated(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_device: MagicMock
) -> None:
    """Test entities belonging to the same JDownloader deduplicate calls."""
    await hass.services.async_call(
        DOMAIN,
        "start_downloads",
        {
            "entity_id": [
                "sensor.jdownloader_mypc_status",
                "switch.jdownloader_mypc_pause",
            ]
        },
        blocking=True,
    )
    mock_device.downloadcontroller.start_downloads.assert_called_once_with()


async def test_deprecated_service_creates_issue(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_device: MagicMock,
    device_registry: dr.DeviceRegistry,
    issue_registry: ir.IssueRegistry,
) -> None:
    """Test calling a deprecated service with device_id creates an issue."""
    jd_device_id = _get_jd_device_id(device_registry, init_integration.entry_id)
    await hass.services.async_call(
        DOMAIN, "start_downloads", {"device_id": jd_device_id}, blocking=True
    )
    mock_device.downloadcontroller.start_downloads.assert_called_once_with()
    issue = issue_registry.async_get_issue(DOMAIN, "deprecated_service_start_downloads")
    assert issue is not None
    # No entity-target issue since device_id was used
    assert issue_registry.async_get_issue(DOMAIN, "deprecated_entity_target") is None


async def test_entity_target_creates_issue(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_device: MagicMock,
    issue_registry: ir.IssueRegistry,
) -> None:
    """Test calling add_links with entity_id creates a deprecation issue."""
    await hass.services.async_call(
        DOMAIN,
        "add_links",
        {"entity_id": STATUS, "links": ["https://example.com/a.zip"]},
        blocking=True,
    )
    issue = issue_registry.async_get_issue(DOMAIN, "deprecated_entity_target")
    assert issue is not None


async def test_add_links_unknown_device(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test add_links raises ServiceValidationError for an unknown device_id."""
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            "add_links",
            {"device_id": "does-not-exist", "links": ["https://example.com/a.zip"]},
            blocking=True,
        )
    assert err.value.translation_key == "device_not_found"


async def test_add_links_account_device(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test add_links raises ServiceValidationError for the account device."""
    account_device_id = _get_account_device_id(
        device_registry, init_integration.entry_id
    )
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            "add_links",
            {
                "device_id": account_device_id,
                "links": ["https://example.com/a.zip"],
            },
            blocking=True,
        )
    assert err.value.translation_key == "device_not_found"


async def test_add_links_entity_not_found(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test add_links raises ServiceValidationError for an entity of another integration."""
    hass.states.async_set("sensor.other", "1")
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            "add_links",
            {"entity_id": "sensor.other", "links": ["https://example.com/a.zip"]},
            blocking=True,
        )
    assert err.value.translation_key == "entity_not_found"


async def test_add_links_device_offline(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_myjdapi: MagicMock,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test add_links raises ServiceValidationError when the JDownloader is offline."""
    jd_device_id = _get_jd_device_id(device_registry, init_integration.entry_id)
    mock_myjdapi.list_devices.return_value = []
    await init_integration.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            "add_links",
            {"device_id": jd_device_id, "links": ["https://example.com/a.zip"]},
            blocking=True,
        )
    assert err.value.translation_key == "device_offline"


async def test_add_links_entry_not_loaded(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_device: MagicMock,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test add_links raises ServiceValidationError when the entry is unloaded."""
    jd_device_id = _get_jd_device_id(device_registry, init_integration.entry_id)
    await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            "add_links",
            {"device_id": jd_device_id, "links": ["https://example.com/a.zip"]},
            blocking=True,
        )
    assert err.value.translation_key == "entry_not_loaded"


async def test_add_links_invalid_priority(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Test add_links raises vol.Invalid for an invalid priority value."""
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            "add_links",
            {
                "entity_id": STATUS,
                "links": ["https://example.com/a.zip"],
                "priority": "urgent",
            },
            blocking=True,
        )


async def test_add_links_any_link_type(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_device: MagicMock,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test magnet links and text are passed to JDownloader's link crawler."""
    jd_device_id = _get_jd_device_id(device_registry, init_integration.entry_id)
    await hass.services.async_call(
        DOMAIN,
        "add_links",
        {
            "device_id": jd_device_id,
            "links": [
                "magnet:?xt=urn:btih:abc",
                " ftp://example.com/f.zip ",
                "see https://example.com/x",
            ],
        },
        blocking=True,
    )
    (params,) = mock_device.linkgrabber.add_links.call_args.args
    assert params[0]["links"] == (
        "magnet:?xt=urn:btih:abc\nftp://example.com/f.zip\nsee https://example.com/x"
    )


async def test_add_links_empty_link(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test blank links are rejected."""
    jd_device_id = _get_jd_device_id(device_registry, init_integration.entry_id)
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            "add_links",
            {"device_id": jd_device_id, "links": ["https://example.com/a", "  "]},
            blocking=True,
        )


async def test_targets_validated_before_any_call(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_myjdapi: MagicMock,
    mock_devices: dict[str, MagicMock],
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test nothing is sent when one of several JDownloaders is offline."""
    coordinator = init_integration.runtime_data.coordinator
    first = mock_myjdapi.list_devices.return_value[0]
    second = {"name": "Laptop", "id": "0123456789abcdef0123456789abcdef", "type": "jd"}
    mock_devices[second["id"]] = _mock_device(second)
    mock_myjdapi.list_devices.return_value = [first, second]
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    device_ids = [
        _get_jd_device_id(device_registry, init_integration.entry_id),
        next(
            device.id
            for device in dr.async_entries_for_config_entry(
                device_registry, init_integration.entry_id
            )
            if (DOMAIN, second["id"]) in device.identifiers
        ),
    ]

    # The second JDownloader goes offline.
    mock_myjdapi.list_devices.return_value = [first]
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            "add_links",
            {"device_id": device_ids, "links": ["https://example.com/a"]},
            blocking=True,
        )
    assert err.value.translation_key == "device_offline"
    for device in mock_devices.values():
        device.linkgrabber.add_links.assert_not_called()
