"""Coordinator for Weider WT16."""

import asyncio
import logging

from modbus_connection import ModbusError
from .vendor.weider_heatpump import WeiderWT16

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, FAILED_POLL_TOLERANCE, RETRY_DELAY, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)
type WeiderConfigEntry = ConfigEntry[WeiderCoordinator]

# Errors that indicate a (usually transient) communication problem. A peer reset
# surfaces as ConnectionResetError, an OSError, if the transport does not wrap it.
COMMUNICATION_ERRORS = (ModbusError, TimeoutError, OSError)


class WeiderCoordinator(DataUpdateCoordinator[WeiderWT16]):
    """Poll the complete device on one schedule.

    Gateways and heat pumps occasionally reset the TCP connection. The shared
    Modbus connection reopens on the next request, so a failed poll is retried
    once right away. If that also fails, the last values are kept for up to
    FAILED_POLL_TOLERANCE consecutive polls before entities become unavailable.
    """

    def __init__(self, hass: HomeAssistant, entry: WeiderConfigEntry, device: WeiderWT16) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, config_entry=entry, update_interval=SCAN_INTERVAL)
        self.device = device
        self.failed_polls = 0

    async def _async_poll(self) -> None:
        """Read the device, retrying once after a communication error."""
        try:
            await self.device.async_update()
        except COMMUNICATION_ERRORS as err:
            _LOGGER.debug("Weider WT16 poll failed (%s), retrying once", err)
            await asyncio.sleep(RETRY_DELAY.total_seconds())
            await self.device.async_update()

    async def _async_update_data(self) -> WeiderWT16:
        try:
            await self._async_poll()
        except COMMUNICATION_ERRORS as err:
            self.failed_polls += 1
            if self.data is None or self.failed_polls >= FAILED_POLL_TOLERANCE:
                raise UpdateFailed(f"Error communicating with Weider WT16: {err}") from err
            _LOGGER.info(
                "Weider WT16 poll failed (%s of %s tolerated), keeping last values: %s",
                self.failed_polls, FAILED_POLL_TOLERANCE - 1, err,
            )
            return self.data
        if self.failed_polls:
            _LOGGER.debug("Weider WT16 poll recovered after %s failed poll(s)", self.failed_polls)
        self.failed_polls = 0
        return self.device
