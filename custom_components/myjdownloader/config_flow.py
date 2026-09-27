"""Config flow for the MyJDownloader integration."""

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .api import MyJDownloaderAuthError, MyJDownloaderClient, MyJDownloaderError
from .const import DOMAIN, TITLE

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Validate the credentials by logging in to MyJDownloader."""
    client = MyJDownloaderClient(hass, data[CONF_EMAIL], data[CONF_PASSWORD])
    await client.async_connect()
    await client.async_disconnect()


class MyJDownloaderConfigFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for MyJDownloader."""

    VERSION = 2

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await validate_input(self.hass, user_input)
            except MyJDownloaderAuthError:
                errors["base"] = "invalid_auth"
            except MyJDownloaderError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=TITLE, data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )
