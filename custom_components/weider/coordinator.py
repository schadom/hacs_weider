"""Coordinator for Weider WT16."""

import logging

from modbus_connection import ModbusError
from .vendor.weider_heatpump import WeiderWT16

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)
type WeiderConfigEntry = ConfigEntry[WeiderCoordinator]


class WeiderCoordinator(DataUpdateCoordinator[WeiderWT16]):
    """Poll the complete device on one schedule."""

    def __init__(self, hass: HomeAssistant, entry: WeiderConfigEntry, device: WeiderWT16) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, config_entry=entry, update_interval=SCAN_INTERVAL)
        self.device = device

    async def _async_update_data(self) -> WeiderWT16:
        try:
            await self.device.async_update()
        except ModbusError as err:
            raise UpdateFailed(f"Error communicating with Weider WT16: {err}") from err
        return self.device

