"""Lifecycle and timing edge cases of the MyJDownloader integration."""

import asyncio
import threading
from unittest.mock import MagicMock

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.myjdownloader.const import DOMAIN
from homeassistant.config_entries import ConfigEntryDisabler, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

STATUS = "sensor.jdownloader_mypc_status"
PAUSE = "switch.jdownloader_mypc_pause"


class _Gate:
    """Block a library call in the executor until released."""

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()

    def __call__(self, *args: object, **kwargs: object) -> str:
        self.entered.set()
        assert self.release.wait(5)
        return "RUNNING"


async def _wait_entered(hass: HomeAssistant, gate: _Gate) -> None:
    assert await hass.async_add_executor_job(gate.entered.wait, 5)


async def test_action_waits_for_running_poll(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_device: MagicMock
) -> None:
    """Test an action during a poll waits for the lock and then runs."""
    gate = _Gate()
    mock_device.downloadcontroller.get_current_state.side_effect = gate
    coordinator = init_integration.runtime_data.coordinator
    poll = hass.async_create_task(coordinator.async_refresh())
    await _wait_entered(hass, gate)

    action = hass.async_create_task(
        hass.services.async_call(
            "switch", "turn_on", {"entity_id": PAUSE}, blocking=True
        )
    )
    await asyncio.sleep(0.05)
    # Serialized: the action has not reached the library yet.
    mock_device.downloadcontroller.pause_downloads.assert_not_called()

    gate.release.set()
    await poll
    await action
    mock_device.downloadcontroller.pause_downloads.assert_called_once_with(True)


async def test_unload_during_poll(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_device: MagicMock,
    mock_myjdapi: MagicMock,
) -> None:
    """Test unloading while a poll runs in the executor finishes cleanly."""
    gate = _Gate()
    mock_device.downloadcontroller.get_current_state.side_effect = gate
    coordinator = init_integration.runtime_data.coordinator
    poll = hass.async_create_task(coordinator.async_refresh())
    await _wait_entered(hass, gate)

    unload = hass.async_create_task(
        hass.config_entries.async_unload(init_integration.entry_id)
    )
    await asyncio.sleep(0.05)
    gate.release.set()
    await poll
    assert await unload
    await hass.async_block_till_done()

    assert init_integration.state is ConfigEntryState.NOT_LOADED
    mock_myjdapi.disconnect.assert_called_once()


async def test_parallel_actions(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_device: MagicMock,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test many actions at once are all executed one after another."""
    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, "af9d03a21ddb917492dc1af8a6427f11"), init_integration.entry_id
    )
    assert device is not None
    active = 0
    overlap = False

    def add_links(params: list[dict[str, object]]) -> None:
        nonlocal active, overlap
        active += 1
        overlap |= active > 1
        threading.Event().wait(0.01)
        active -= 1

    mock_device.linkgrabber.add_links.side_effect = add_links
    await asyncio.gather(
        *(
            hass.services.async_call(
                DOMAIN,
                "add_links",
                {"device_id": device.id, "links": [f"https://example.com/{i}"]},
                blocking=True,
            )
            for i in range(10)
        )
    )
    assert mock_device.linkgrabber.add_links.call_count == 10
    assert not overlap


async def test_reload_repeatedly(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_myjdapi: MagicMock
) -> None:
    """Test every reload closes the session it opened."""
    for _ in range(5):
        assert await hass.config_entries.async_reload(init_integration.entry_id)
        await hass.async_block_till_done()
    assert init_integration.state is ConfigEntryState.LOADED
    # One login per setup (initial + 5 reloads), one logout per unload.
    assert mock_myjdapi.connect.call_count == 6
    assert mock_myjdapi.disconnect.call_count == 5
    assert hass.states.get(STATUS).state == "running"


async def test_disable_and_enable_entry(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_myjdapi: MagicMock
) -> None:
    """Test disabling logs out and enabling restores the entities."""
    assert await hass.config_entries.async_set_disabled_by(
        init_integration.entry_id, ConfigEntryDisabler.USER
    )
    await hass.async_block_till_done()
    assert init_integration.state is ConfigEntryState.NOT_LOADED
    mock_myjdapi.disconnect.assert_called_once()

    assert await hass.config_entries.async_set_disabled_by(
        init_integration.entry_id, None
    )
    await hass.async_block_till_done()
    assert init_integration.state is ConfigEntryState.LOADED
    assert hass.states.get(STATUS).state == "running"


async def test_reload_while_device_offline(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_myjdapi: MagicMock
) -> None:
    """Test a known JDownloader offline at startup keeps unavailable entities."""
    mock_myjdapi.list_devices.return_value = []
    assert await hass.config_entries.async_reload(init_integration.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(STATUS).state == "unavailable"
    assert hass.states.get("binary_sensor.jdownloader_mypc_connected").state == "off"


async def test_renamed_device(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_myjdapi: MagicMock,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test renaming the JDownloader keeps entity ids and updates the device."""
    mock_myjdapi.list_devices.return_value = [
        {"name": "Office", "id": "af9d03a21ddb917492dc1af8a6427f11", "type": "jd"}
    ]
    await init_integration.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(STATUS).state == "running"

    assert await hass.config_entries.async_reload(init_integration.entry_id)
    await hass.async_block_till_done()
    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, "af9d03a21ddb917492dc1af8a6427f11"), init_integration.entry_id
    )
    assert device is not None
    assert device.name == "JDownloader Office"
    # Entity ids are stored in the registry and do not follow the new name.
    assert hass.states.get(STATUS).state == "running"
