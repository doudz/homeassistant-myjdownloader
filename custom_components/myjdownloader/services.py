"""Actions of the MyJDownloader integration."""

from collections.abc import Callable
import logging
from typing import Any

from myjdapi.myjdapi import Jddevice
import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_DEVICE_ID, ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)

from .const import (
    DOMAIN,
    FIELD_AUTO_EXTRACT,
    FIELD_AUTOSTART,
    FIELD_DESTINATION_FOLDER,
    FIELD_DOWNLOAD_PASSWORD,
    FIELD_EXTRACT_PASSWORD,
    FIELD_LINKS,
    FIELD_OVERWRITE_PACKAGIZER_RULES,
    FIELD_PACKAGE_NAME,
    FIELD_PRIORITY,
    SERVICE_ADD_LINKS,
    SERVICE_RESTART_AND_UPDATE,
    SERVICE_RUN_UPDATE_CHECK,
    SERVICE_START_DOWNLOADS,
    SERVICE_STOP_DOWNLOADS,
)
from .coordinator import MyJDownloaderConfigEntry, MyJDownloaderCoordinator

_LOGGER = logging.getLogger(__name__)

PRIORITIES = ["highest", "higher", "high", "default", "low", "lower", "lowest"]

# Targets: device_id is the documented way. entity_id is still accepted
# for automations written for versions before 3.0 (deprecated).
TARGET_SCHEMA: dict[vol.Marker, Any] = {
    vol.Optional(ATTR_DEVICE_ID): vol.All(cv.ensure_list, [cv.string]),
    vol.Optional(ATTR_ENTITY_ID): cv.entity_ids,
}

ADD_LINKS_SCHEMA = vol.All(
    vol.Schema(
        {
            **TARGET_SCHEMA,
            # Anything JDownloader's link crawler understands: http(s), magnet,
            # ftp, container links or text containing links.
            vol.Required(FIELD_LINKS): vol.All(
                cv.ensure_list, [vol.All(cv.string, vol.Strip, vol.Length(min=1))]
            ),
            vol.Optional(FIELD_PRIORITY, default="default"): vol.All(
                cv.string, vol.Lower, vol.In(PRIORITIES)
            ),
            vol.Optional(FIELD_PACKAGE_NAME): cv.string,
            vol.Optional(FIELD_AUTOSTART, default=False): cv.boolean,
            vol.Optional(FIELD_AUTO_EXTRACT, default=False): cv.boolean,
            vol.Optional(FIELD_EXTRACT_PASSWORD): cv.string,
            vol.Optional(FIELD_DOWNLOAD_PASSWORD): cv.string,
            vol.Optional(FIELD_DESTINATION_FOLDER): cv.string,
            vol.Optional(FIELD_OVERWRITE_PACKAGIZER_RULES, default=False): cv.boolean,
        }
    ),
    cv.has_at_least_one_key(ATTR_DEVICE_ID, ATTR_ENTITY_ID),
)
DEVICE_SCHEMA = vol.All(
    vol.Schema(TARGET_SCHEMA),
    cv.has_at_least_one_key(ATTR_DEVICE_ID, ATTR_ENTITY_ID),
)

# Deprecated actions and the entities replacing them.
DEPRECATED_SERVICES: dict[str, tuple[str, Callable[[Jddevice], Any]]] = {
    SERVICE_START_DOWNLOADS: (
        "button.press on the Start downloads button",
        lambda device: device.downloadcontroller.start_downloads(),
    ),
    SERVICE_STOP_DOWNLOADS: (
        "button.press on the Stop downloads button",
        lambda device: device.downloadcontroller.stop_downloads(),
    ),
    SERVICE_RUN_UPDATE_CHECK: (
        "button.press on the Run update check button",
        lambda device: device.update.run_update_check(),
    ),
    SERVICE_RESTART_AND_UPDATE: (
        "update.install on the Update entity",
        lambda device: device.update.restart_and_update(),
    ),
}


@callback
def _async_resolve_targets(
    hass: HomeAssistant, call: ServiceCall
) -> list[tuple[MyJDownloaderCoordinator, str]]:
    """Return coordinator and JDownloader id of every targeted JDownloader."""
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    device_ids: list[str] = list(call.data.get(ATTR_DEVICE_ID, []))
    if entity_ids := call.data.get(ATTR_ENTITY_ID):
        ir.async_create_issue(
            hass,
            DOMAIN,
            "deprecated_entity_target",
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="deprecated_entity_target",
            translation_placeholders={"service": f"{DOMAIN}.{call.service}"},
        )
        for entity_id in entity_ids:
            entity = entity_registry.async_get(entity_id)
            if entity is None or entity.platform != DOMAIN or entity.device_id is None:
                raise ServiceValidationError(
                    translation_domain=DOMAIN,
                    translation_key="entity_not_found",
                    translation_placeholders={"entity_id": entity_id},
                )
            device_ids.append(entity.device_id)

    targets: list[tuple[MyJDownloaderCoordinator, str]] = []
    for device_id in dict.fromkeys(device_ids):  # deduplicated, ordered
        device = device_registry.async_get(device_id)
        jd_id = (
            next(
                (
                    identifier
                    for domain, identifier in device.identifiers
                    if domain == DOMAIN and not identifier.startswith("account_")
                ),
                None,
            )
            if device is not None
            else None
        )
        if device is None or jd_id is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="device_not_found",
                translation_placeholders={"device_id": device_id},
            )
        entry: MyJDownloaderConfigEntry | None = hass.config_entries.async_get_entry(
            device.config_entry_id
        )
        if entry is None or entry.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="entry_not_loaded",
                translation_placeholders={"device": device.name or device_id},
            )
        coordinator = entry.runtime_data.coordinator
        state = coordinator.data.devices.get(jd_id)
        if state is None or not state.online:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="device_offline",
                translation_placeholders={"device": device.name or device_id},
            )
        targets.append((coordinator, jd_id))
    return targets


async def _async_add_links(call: ServiceCall) -> None:
    """Add links to the LinkGrabber of the targeted JDownloaders."""
    data = call.data
    # https://my.jdownloader.org/developers/index.html#tag_244
    params = [
        {
            "autoExtract": data[FIELD_AUTO_EXTRACT],
            "autostart": data[FIELD_AUTOSTART],
            "destinationFolder": data.get(FIELD_DESTINATION_FOLDER),
            "downloadPassword": data.get(FIELD_DOWNLOAD_PASSWORD),
            "extractPassword": data.get(FIELD_EXTRACT_PASSWORD),
            "links": "\n".join(data[FIELD_LINKS]),
            "overwritePackagizerRules": data[FIELD_OVERWRITE_PACKAGIZER_RULES],
            "packageName": data.get(FIELD_PACKAGE_NAME),
            "priority": data[FIELD_PRIORITY].upper(),
        }
    ]
    for coordinator, jd_id in _async_resolve_targets(call.hass, call):
        await coordinator.async_device_action(
            jd_id, lambda device: device.linkgrabber.add_links(params)
        )


async def _async_deprecated_service(call: ServiceCall) -> None:
    """Run a deprecated action and point to its replacement."""
    replacement, func = DEPRECATED_SERVICES[call.service]
    _LOGGER.warning(
        "The action %s.%s is deprecated and will be removed in 3.2, use %s instead",
        DOMAIN,
        call.service,
        replacement,
    )
    ir.async_create_issue(
        call.hass,
        DOMAIN,
        f"deprecated_service_{call.service}",
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="deprecated_service",
        translation_placeholders={
            "service": f"{DOMAIN}.{call.service}",
            "replacement": replacement,
        },
    )
    for coordinator, jd_id in _async_resolve_targets(call.hass, call):
        await coordinator.async_device_action(jd_id, func)


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the MyJDownloader actions."""
    hass.services.async_register(
        DOMAIN, SERVICE_ADD_LINKS, _async_add_links, schema=ADD_LINKS_SCHEMA
    )
    for service in DEPRECATED_SERVICES:
        hass.services.async_register(
            DOMAIN, service, _async_deprecated_service, schema=DEVICE_SCHEMA
        )
