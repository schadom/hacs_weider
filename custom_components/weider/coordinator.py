"""Coordinator for Weider heat pumps."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime
import logging

from modbus_connection import ModbusError
from weider_modbus import WeiderWT16

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    FAILED_POLL_TOLERANCE,
    PENDING_TARGET_TIMEOUT,
    RETRY_DELAY,
    SCAN_INTERVAL,
)

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
        # Written targets that no poll has confirmed yet: key -> (value, deadline).
        self._pending_targets: dict[str, tuple[float, datetime]] = {}

    def target(self, key: str) -> float | None:
        """Return a target setting, or its newly written value until confirmed."""
        if (pending := self._pending_targets.get(key)) is not None:
            return pending[0]
        value: float | None = getattr(self.device.settings, key)
        return value

    async def async_write_target(
        self, key: str, write: Callable[[WeiderWT16], Awaitable[None]], value: float
    ) -> None:
        """Write a target and show the new value right away.

        The heat pump refreshes its Modbus values only about once a minute, so
        an immediate poll could still return the old target. The new value is
        shown until a regular poll confirms it.
        """
        await write(self.device)
        self._pending_targets[key] = (value, dt_util.utcnow() + PENDING_TARGET_TIMEOUT)
        self.async_update_listeners()

    def _resolve_pending_targets(self) -> None:
        """Drop written targets that a poll confirmed or that timed out."""
        now = dt_util.utcnow()
        for key, (value, deadline) in list(self._pending_targets.items()):
            current = getattr(self.device.settings, key)
            if current is not None and round(current, 1) == round(value, 1):
                del self._pending_targets[key]
            elif now >= deadline:
                del self._pending_targets[key]
                _LOGGER.warning(
                    "The heat pump still reports %s = %s after writing %s; showing the reported value",
                    key, current, value,
                )

    async def _async_poll(self) -> None:
        """Read the device, retrying once after a communication error."""
        try:
            await self.device.async_update()
        except COMMUNICATION_ERRORS as err:
            _LOGGER.debug("Weider poll failed (%s), retrying once", err)
            await asyncio.sleep(RETRY_DELAY.total_seconds())
            await self.device.async_update()

    async def _async_update_data(self) -> WeiderWT16:
        try:
            await self._async_poll()
        except COMMUNICATION_ERRORS as err:
            self.failed_polls += 1
            if self.data is None or self.failed_polls >= FAILED_POLL_TOLERANCE:
                raise UpdateFailed(f"Error communicating with the Weider heat pump: {err}") from err
            _LOGGER.info(
                "Weider poll failed (%s of %s tolerated), keeping last values: %s",
                self.failed_polls, FAILED_POLL_TOLERANCE - 1, err,
            )
            return self.data
        if self.failed_polls:
            _LOGGER.debug("Weider poll recovered after %s failed poll(s)", self.failed_polls)
        self.failed_polls = 0
        self._resolve_pending_targets()
        return self.device
