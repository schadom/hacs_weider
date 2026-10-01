"""Config flow for Weider WT16."""

from typing import Any

from modbus_connection import ModbusError, ModbusTcpParams
import voluptuous as vol

from homeassistant.components.modbus import async_get_temporary_unit
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import NumberSelector, NumberSelectorConfig, NumberSelectorMode, TextSelector

from .const import CONF_UNIT_ID, DEFAULT_PORT, DEFAULT_UNIT_ID, DOMAIN
from .vendor.weider_heatpump import WeiderWT16

STEP_USER = vol.Schema({
    vol.Required(CONF_HOST): vol.All(TextSelector(), vol.Length(min=1)),
    vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(NumberSelector(NumberSelectorConfig(min=1, max=65535, step=1, mode=NumberSelectorMode.BOX)), vol.Coerce(int)),
    vol.Required(CONF_UNIT_ID, default=DEFAULT_UNIT_ID): vol.All(NumberSelector(NumberSelectorConfig(min=1, max=247, step=1, mode=NumberSelectorMode.BOX)), vol.Coerce(int)),
})


class WeiderConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configure a Weider WT16."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Configure a new device."""
        return await self._async_configure("user", user_input)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Change connection details while preserving entity identities."""
        return await self._async_configure("reconfigure", user_input)

    async def _async_configure(self, step_id: str, user_input: dict[str, Any] | None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry() if step_id == "reconfigure" else None
        if user_input is not None:
            user_input = {
                CONF_HOST: user_input[CONF_HOST].strip().lower(),
                CONF_PORT: int(user_input[CONF_PORT]),
                CONF_UNIT_ID: int(user_input[CONF_UNIT_ID]),
            }
            unique_id = f"{user_input[CONF_HOST]}_{user_input[CONF_PORT]}_{user_input[CONF_UNIT_ID]}"
            await self.async_set_unique_id(unique_id)
            if entry is None:
                self._abort_if_unique_id_configured()
            elif any(other.unique_id == unique_id and other.entry_id != entry.entry_id for other in self._async_current_entries()):
                return self.async_abort(reason="already_configured")
            try:
                if not user_input[CONF_HOST]:
                    raise ValueError("Host must not be empty")
                params = ModbusTcpParams(host=user_input[CONF_HOST], port=user_input[CONF_PORT])
                async with async_get_temporary_unit(self.hass, params, user_input[CONF_UNIT_ID]) as unit:
                    await WeiderWT16(unit).async_update()
            except (ModbusError, HomeAssistantError, OSError, TimeoutError, ValueError):
                errors["base"] = "cannot_connect"
            else:
                if entry is not None:
                    return self.async_update_reload_and_abort(entry, unique_id=unique_id, data=user_input)
                return self.async_create_entry(title="Weider WT16", data=user_input)
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(STEP_USER, user_input or (entry.data if entry else {})),
            errors=errors,
        )

