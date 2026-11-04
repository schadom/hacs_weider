"""The Weider integration."""

from homeassistant.components.modbus import async_get_unit
from homeassistant.const import CONF_DEVICE, CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError

from .connection import connection_params, create_device
from .const import CONF_UNIT_ID
from .coordinator import WeiderConfigEntry, WeiderCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.CLIMATE, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: WeiderConfigEntry) -> bool:
    """Set up a Weider heat pump using a shared Modbus Connection unit."""
    has_network = CONF_HOST in entry.data and CONF_PORT in entry.data
    if not has_network and CONF_DEVICE not in entry.data:
        raise ConfigEntryError(
            "The legacy Modbus connection reference is no longer supported. "
            "Reconfigure this Weider entry with the heat pump's connection details."
        )
    unit = async_get_unit(
        hass, entry, connection_params(entry.data), int(entry.data[CONF_UNIT_ID])
    )
    coordinator = WeiderCoordinator(hass, entry, create_device(entry.data, unit))
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WeiderConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
