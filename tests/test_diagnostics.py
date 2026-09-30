"""Tests for the MyJDownloader diagnostics."""

import json

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
    get_diagnostics_for_device,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator
from syrupy.assertion import SnapshotAssertion
from syrupy.filters import props

from custom_components.myjdownloader.const import DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .conftest import TEST_EMAIL, TEST_PASSWORD

VOLATILE = props("entry_id", "created_at", "modified_at")


async def test_entry_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    init_integration: MockConfigEntry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test config entry diagnostics are redacted."""
    diagnostics = await get_diagnostics_for_config_entry(
        hass, hass_client, init_integration
    )

    dumped = json.dumps(diagnostics)
    assert TEST_EMAIL not in dumped
    assert TEST_PASSWORD not in dumped
    # Download contents (file names, URLs) are not included, only counts.
    assert "packages" not in diagnostics["devices"][0]
    assert diagnostics == snapshot(exclude=VOLATILE)


async def test_device_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    init_integration: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    snapshot: SnapshotAssertion,
) -> None:
    """Test JDownloader and account device diagnostics."""
    devices = {
        identifier: device
        for device in dr.async_entries_for_config_entry(
            device_registry, init_integration.entry_id
        )
        for domain, identifier in device.identifiers
        if domain == DOMAIN
    }
    jdownloader = devices["af9d03a21ddb917492dc1af8a6427f11"]
    account = devices[f"account_{init_integration.entry_id}"]

    assert await get_diagnostics_for_device(
        hass, hass_client, init_integration, jdownloader
    ) == snapshot(exclude=VOLATILE)

    account_diagnostics = await get_diagnostics_for_device(
        hass, hass_client, init_integration, account
    )
    assert TEST_EMAIL not in json.dumps(account_diagnostics)
    assert account_diagnostics["devices"]
