"""Diagnostics of the MyJDownloader integration."""

from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .coordinator import DeviceState, MyJDownloaderConfigEntry

TO_REDACT = {CONF_EMAIL, CONF_PASSWORD, "title", "unique_id"}


def _library_version() -> str | None:
    try:
        return version("myjdapi")
    except PackageNotFoundError:
        return None


def _device(state: DeviceState) -> dict[str, Any]:
    """Return the state of a JDownloader without download contents.

    Package and link lists contain file names, URLs and passwords, so only
    their size is included.
    """
    data = asdict(state)
    for key in ("packages", "links"):
        items = data.pop(key)
        data[f"{key}_count"] = len(items) if items is not None else None
    data["status"] = state.status
    return data


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MyJDownloaderConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    runtime_data = entry.runtime_data
    coordinator = runtime_data.coordinator
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        # importlib.metadata reads from disk, keep it out of the event loop.
        "myjdapi_version": await hass.async_add_executor_job(_library_version),
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "last_exception": repr(coordinator.last_exception)
            if coordinator.last_exception
            else None,
            "update_interval": coordinator.update_interval.total_seconds()
            if coordinator.update_interval
            else None,
        },
        "latest_version": runtime_data.update_coordinator.data,
        "devices": [_device(state) for state in coordinator.data.devices.values()],
    }


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: MyJDownloaderConfigEntry, device: dr.DeviceEntry
) -> dict[str, Any]:
    """Return diagnostics for a JDownloader or the account device."""
    coordinator = entry.runtime_data.coordinator
    for domain, identifier in device.identifiers:
        if domain == DOMAIN and (state := coordinator.data.devices.get(identifier)):
            return {
                "device": _device(state),
                "last_update_success": coordinator.last_update_success,
            }
    return await async_get_config_entry_diagnostics(hass, entry)
