"""Config flow for Weider heat pumps."""

from collections.abc import Mapping
from typing import Any

from modbus_connection import ModbusError
import voluptuous as vol

from homeassistant.components.modbus import async_get_temporary_unit
from homeassistant.config_entries import SOURCE_RECONFIGURE, ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_DEVICE, CONF_HOST, CONF_PORT
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    SerialPortSelector,
    TextSelector,
)

from .connection import connection_params, connection_type, create_device, location, unique_id
from .const import (
    BAUDRATES,
    CONF_BAUDRATE,
    CONF_CONNECTION_TYPE,
    CONF_PARITY,
    CONF_STOPBITS,
    CONF_UNIT_ID,
    CONNECTION_RTU_OVER_TCP,
    CONNECTION_SERIAL,
    CONNECTION_TCP,
    CONNECTION_TYPES,
    DEFAULT_BAUDRATE,
    DEFAULT_PARITY,
    DEFAULT_PORT,
    DEFAULT_STOPBITS,
    DEFAULT_UNIT_ID,
    DOMAIN,
    PARITIES,
    STOPBITS,
)

_HOST = vol.All(TextSelector(), vol.Length(min=1))
# Dialog option for each stored parity.
_PARITY_OPTION = {parity: option for option, parity in PARITIES.items()}
_PORT = vol.All(
    NumberSelector(NumberSelectorConfig(min=1, max=65535, step=1, mode=NumberSelectorMode.BOX)),
    vol.Coerce(int),
)
_UNIT_ID = vol.All(
    NumberSelector(NumberSelectorConfig(min=1, max=247, step=1, mode=NumberSelectorMode.BOX)),
    vol.Coerce(int),
)


def _choice(options: list[Any], translation_key: str | None = None) -> vol.All:
    """Return a dropdown of the given options that yields the option's type."""
    config = SelectSelectorConfig(
        options=[str(option) for option in options], mode=SelectSelectorMode.DROPDOWN
    )
    if translation_key is not None:
        config["translation_key"] = translation_key
    selector = SelectSelector(config)
    # The selector only accepts the listed options.
    return vol.All(selector, vol.Coerce(type(options[0])))


# Modbus TCP through the Ethernet board.
STEP_TCP = vol.Schema({
    vol.Required(CONF_HOST): _HOST,
    vol.Required(CONF_PORT, default=DEFAULT_PORT): _PORT,
    vol.Required(CONF_UNIT_ID, default=DEFAULT_UNIT_ID): _UNIT_ID,
})
# Modbus RTU on the RS485 port, through a serial port of the Home Assistant host.
STEP_SERIAL = vol.Schema({
    vol.Required(CONF_DEVICE): vol.All(SerialPortSelector(), vol.Length(min=1)),
    vol.Required(CONF_BAUDRATE, default=str(DEFAULT_BAUDRATE)): _choice(BAUDRATES),
    vol.Required(CONF_PARITY, default=_PARITY_OPTION[DEFAULT_PARITY]): _choice(
        list(PARITIES), "parity"
    ),
    vol.Required(CONF_STOPBITS, default=str(DEFAULT_STOPBITS)): _choice(STOPBITS),
    vol.Required(CONF_UNIT_ID, default=DEFAULT_UNIT_ID): _UNIT_ID,
})
# Modbus RTU on the RS485 port, through a converter on the network.
STEP_RTU_OVER_TCP = vol.Schema({
    vol.Required(CONF_HOST): _HOST,
    vol.Required(CONF_PORT): _PORT,
    vol.Required(CONF_UNIT_ID, default=DEFAULT_UNIT_ID): _UNIT_ID,
})
SCHEMAS = {
    CONNECTION_TCP: STEP_TCP,
    CONNECTION_SERIAL: STEP_SERIAL,
    CONNECTION_RTU_OVER_TCP: STEP_RTU_OVER_TCP,
}


def _entry_data(kind: str, user_input: Mapping[str, Any]) -> dict[str, Any]:
    """Return the entry data for the form input, with normalized values."""
    data: dict[str, Any] = {CONF_CONNECTION_TYPE: kind}
    if kind == CONNECTION_SERIAL:
        data[CONF_DEVICE] = user_input[CONF_DEVICE].strip()
        data[CONF_BAUDRATE] = int(user_input[CONF_BAUDRATE])
        parity = user_input[CONF_PARITY]
        data[CONF_PARITY] = PARITIES.get(parity, parity)
        data[CONF_STOPBITS] = int(user_input[CONF_STOPBITS])
    else:
        data[CONF_HOST] = user_input[CONF_HOST].strip().lower()
        data[CONF_PORT] = int(user_input[CONF_PORT])
    data[CONF_UNIT_ID] = int(user_input[CONF_UNIT_ID])
    return data


def _form_values(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return entry data as form values; dropdowns hold their options as text."""
    values = {key: value for key, value in data.items() if key != CONF_CONNECTION_TYPE}
    for key in (CONF_BAUDRATE, CONF_STOPBITS):
        if key in values:
            values[key] = str(values[key])
    if CONF_PARITY in values:
        values[CONF_PARITY] = _PARITY_OPTION[values[CONF_PARITY]]
    return values


class WeiderConfigFlow(ConfigFlow, domain=DOMAIN):
    """Configure a Weider heat pump."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask how Home Assistant connects to the heat pump."""
        if user_input is not None:
            # Input passed directly to the flow, without the menu.
            return await self._async_configure(_input_type(user_input), user_input)
        return self.async_show_menu(step_id="user", menu_options=CONNECTION_TYPES)

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Change connection details while preserving entity identities."""
        if user_input is not None:
            return await self._async_configure(_input_type(user_input), user_input)
        return self.async_show_menu(step_id="reconfigure", menu_options=CONNECTION_TYPES)

    async def async_step_tcp(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Connect over Modbus TCP."""
        return await self._async_configure(CONNECTION_TCP, user_input)

    async def async_step_serial(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Connect over Modbus RTU through a serial port."""
        return await self._async_configure(CONNECTION_SERIAL, user_input)

    async def async_step_rtu_over_tcp(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Connect over Modbus RTU through a converter on the network."""
        return await self._async_configure(CONNECTION_RTU_OVER_TCP, user_input)

    def _title(self, data: Mapping[str, Any]) -> str:
        """Name the first heat pump plainly and tell further ones apart."""
        if not self._async_current_entries(include_ignore=False):
            return "Weider"
        return f"Weider ({location(data)}, unit {data[CONF_UNIT_ID]})"

    async def _async_configure(self, kind: str, user_input: dict[str, Any] | None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry() if self.source == SOURCE_RECONFIGURE else None
        if user_input is not None:
            data = _entry_data(kind, user_input)
            entry_unique_id = unique_id(data)
            await self.async_set_unique_id(entry_unique_id)
            if entry is None:
                self._abort_if_unique_id_configured()
            elif any(
                other.unique_id == entry_unique_id and other.entry_id != entry.entry_id
                for other in self._async_current_entries()
            ):
                return self.async_abort(reason="already_configured")
            try:
                if not data.get(CONF_HOST, data.get(CONF_DEVICE)):
                    raise ValueError("Host or serial port must not be empty")
                params = connection_params(data)
                async with async_get_temporary_unit(self.hass, params, data[CONF_UNIT_ID]) as unit:
                    await create_device(data, unit).async_update()
            except (ModbusError, HomeAssistantError, OSError, TimeoutError, ValueError):
                errors["base"] = "cannot_connect"
            else:
                if entry is not None:
                    return self.async_update_reload_and_abort(
                        entry, unique_id=entry_unique_id, data=data
                    )
                return self.async_create_entry(title=self._title(data), data=data)
        if user_input is not None:
            suggested: Mapping[str, Any] = user_input
        elif entry is not None and connection_type(entry.data) == kind:
            suggested = _form_values(entry.data)
        else:
            suggested = {}
        return self.async_show_form(
            step_id=kind,
            data_schema=self.add_suggested_values_to_schema(SCHEMAS[kind], suggested),
            errors=errors,
        )


def _input_type(user_input: Mapping[str, Any]) -> str:
    """Return the connection type of input passed to the flow without the menu."""
    if CONF_CONNECTION_TYPE in user_input:
        return str(user_input[CONF_CONNECTION_TYPE])
    return CONNECTION_SERIAL if CONF_DEVICE in user_input else CONNECTION_TCP
