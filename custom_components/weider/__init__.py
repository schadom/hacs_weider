"""The Weider WT16 integration."""

from modbus_connection import ModbusTcpParams

from homeassistant.components.modbus import async_get_unit
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError

from .const import CONF_UNIT_ID
from .coordinator import WeiderConfigEntry, WeiderCoordinator
from .vendor.weider_heatpump import WeiderWT16

PLATFORMS = [Platform.BINARY_SENSOR, Platform.CLIMATE, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: WeiderConfigEntry) -> bool:
    """Set up a WT16 using a shared Modbus Connection unit."""
    if CONF_HOST not in entry.data or CONF_PORT not in entry.data:
        raise ConfigEntryError(
            "The legacy Modbus connection reference is no longer supported. "
            "Reconfigure this Weider entry with the heat pump's host and TCP port."
        )
    unit = async_get_unit(
        hass,
        entry,
        ModbusTcpParams(host=entry.data[CONF_HOST], port=entry.data[CONF_PORT]),
        int(entry.data[CONF_UNIT_ID]),
    )
    coordinator = WeiderCoordinator(hass, entry, WeiderWT16(unit))
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: WeiderConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

