"""Typed Modbus component models for the Weider WT16."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Final

from modbus_connection.exceptions import IllegalDataAddressError
from modbus_connection.model import Component, discrete_input, gauge, integer, string, uint32

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PointInfo:
    """Application-neutral metadata for a public data point."""

    key: str
    name: str
    component: str
    unit: str | None = None
    device_class: str | None = None
    writable: bool = False
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None


def _temperature(address: int, *, writable: bool = False):
    """Return the unsigned 0.1-scaled WT16 temperature format."""
    return gauge(address, 0.1, signed=False, unit="°C", writable=writable)


class Measurements(Component):
    """Read-only WT16 input registers (function code 04)."""

    register_space = "input"
    max_gap = 0
    max_span = 50

    hot_water_temperature = _temperature(13)
    flow_target_temperature = _temperature(14)
    outdoor_temperature = _temperature(15)
    buffer_temperature = _temperature(16)
    mixer_temperature = _temperature(17)
    reserve_temperature_1 = _temperature(18)
    reserve_temperature_2 = _temperature(19)
    reserve_temperature_3 = _temperature(20)
    defrost_temperature = _temperature(21)
    flow_temperature = _temperature(25)
    return_temperature = _temperature(26)
    source_inlet_temperature = _temperature(27)
    source_outlet_temperature = _temperature(28)
    superheat = _temperature(29)
    evaporation_temperature = _temperature(31)
    condensation_temperature = _temperature(33)
    evaporator_temperature = _temperature(35)
    suction_gas_temperature = _temperature(36)
    hot_gas_temperature = _temperature(37)
    volume_flow = gauge(44, 0.001, signed=False, unit="m³/h")
    room_temperature = _temperature(724)
    mixer_position = integer(736, signed=False)
    last_pump_runtime = uint32(60164, unit="min")
    last_hot_water_runtime = uint32(60168, unit="min")
    active_error = string(63000, 16)


class Settings(Component):
    """Writable WT16 holding registers (function codes 03/16)."""

    max_gap = 0
    max_span = 50
    hot_water_target_temperature = gauge(
        1, 0.1, signed=False, unit="°C", writable=True, force_fc16=True
    )
    room_target_temperature = gauge(
        723, 0.1, signed=False, unit="°C", writable=True, force_fc16=True
    )


class DigitalInputs(Component):
    """WT16 discrete inputs (function code 02)."""

    max_gap = 0
    max_span = 1
    flow_switch_1 = discrete_input(45)
    flow_switch_2 = discrete_input(69)
    compressor = discrete_input(679)
    heating_pump = discrete_input(680)
    source_pump = discrete_input(681)
    mixer_pump = discrete_input(682)
    hot_water_pump = discrete_input(685)
    remote_fault = discrete_input(686)
    four_way_valve = discrete_input(690)
    reserve_1 = discrete_input(691)
    reserve_2 = discrete_input(692)
    reserve_3 = discrete_input(693)
    cooling_output = discrete_input(694)
    reserve_5 = discrete_input(695)
    hot_water_block = discrete_input(703)
    heating_block = discrete_input(704)
    utility_block = discrete_input(705)
    sg_ready_1 = discrete_input(706)
    sg_ready_2 = discrete_input(707)
    reserve = discrete_input(714)

    async def async_update(self, *, notify: bool = True) -> None:
        """Refresh supported inputs, excluding addresses rejected by this device."""
        while True:
            try:
                await super().async_update(notify=notify)
                return
            except IllegalDataAddressError as err:
                block = err.block
                if block is None or block.space != "discrete" or block.count != 1:
                    raise
                unsupported = {
                    name for name, field in self.resolved_fields.items()
                    if field.address == block.address
                }
                if not unsupported:
                    raise
                self.restrict_fields(set(self.resolved_fields) - unsupported)
                _LOGGER.warning(
                    "Skipping unsupported digital input(s) %s at address %s",
                    ", ".join(sorted(unsupported)), block.address,
                )


POINTS: Final[tuple[PointInfo, ...]] = (
    PointInfo("hot_water_target_temperature", "Hot water target temperature", "settings", "°C", "temperature", True, 15, 55, 0.5),
    PointInfo("room_target_temperature", "Room target temperature", "settings", "°C", "temperature", True, 15, 35, 0.5),
    PointInfo("hot_water_temperature", "Hot water temperature", "measurements", "°C", "temperature"),
    PointInfo("room_temperature", "Room temperature", "measurements", "°C", "temperature"),
    PointInfo("flow_target_temperature", "Flow target temperature", "measurements", "°C", "temperature"),
    PointInfo("flow_temperature", "Flow temperature", "measurements", "°C", "temperature"),
    PointInfo("outdoor_temperature", "Outdoor temperature", "measurements", "°C", "temperature"),
    PointInfo("buffer_temperature", "Buffer temperature", "measurements", "°C", "temperature"),
    PointInfo("mixer_temperature", "Mixer temperature", "measurements", "°C", "temperature"),
    PointInfo("reserve_temperature_1", "Reserve sensor temperature 1", "measurements", "°C", "temperature"),
    PointInfo("reserve_temperature_2", "Reserve sensor temperature 2", "measurements", "°C", "temperature"),
    PointInfo("reserve_temperature_3", "Reserve sensor temperature 3", "measurements", "°C", "temperature"),
    PointInfo("defrost_temperature", "Defrost sensor temperature", "measurements", "°C", "temperature"),
    PointInfo("return_temperature", "Return temperature", "measurements", "°C", "temperature"),
    PointInfo("source_inlet_temperature", "Source inlet temperature", "measurements", "°C", "temperature"),
    PointInfo("source_outlet_temperature", "Source outlet temperature", "measurements", "°C", "temperature"),
    PointInfo("superheat", "Superheat", "measurements", "°C", "temperature"),
    PointInfo("evaporation_temperature", "Evaporation temperature", "measurements", "°C", "temperature"),
    PointInfo("condensation_temperature", "Condensation temperature", "measurements", "°C", "temperature"),
    PointInfo("evaporator_temperature", "Evaporator temperature", "measurements", "°C", "temperature"),
    PointInfo("suction_gas_temperature", "Suction gas temperature", "measurements", "°C", "temperature"),
    PointInfo("hot_gas_temperature", "Hot gas temperature", "measurements", "°C", "temperature"),
    PointInfo("volume_flow", "Volume flow", "measurements", "m³/h", "volume_flow_rate"),
    PointInfo("active_error", "Active error", "measurements"),
    PointInfo("last_pump_runtime", "Last pump runtime", "measurements", "min", "duration"),
    PointInfo("last_hot_water_runtime", "Last hot water runtime", "measurements", "min", "duration"),
    PointInfo("mixer_position", "Mixer position", "measurements"),
)

BINARY_POINTS: Final[tuple[PointInfo, ...]] = tuple(
    PointInfo(key, name, "digital_inputs", device_class=device_class)
    for key, name, device_class in (
        ("flow_switch_1", "Flow switch 1", None), ("flow_switch_2", "Flow switch 2", None),
        ("remote_fault", "Remote fault", "problem"), ("compressor", "Compressor", None),
        ("heating_pump", "Heating pump", None), ("source_pump", "Source / water / fan pump", None),
        ("mixer_pump", "Mixer pump", None), ("hot_water_pump", "Hot water pump", None),
        ("four_way_valve", "Four-way valve", None), ("reserve_1", "Reserve 1", None),
        ("reserve_2", "Reserve 2", None), ("reserve_3", "Reserve 3", None),
        ("cooling_output", "Reserve 4 cooling output", None), ("reserve_5", "Reserve 5", None),
        ("hot_water_block", "Hot water block", None), ("heating_block", "Heating block", None),
        ("utility_block", "Utility company block", None), ("sg_ready_1", "SG Ready 1", None),
        ("sg_ready_2", "SG Ready 2", None), ("reserve", "Reserve", None),
    )
)


class WeiderWT16:
    """Application-neutral representation of one Weider WT16."""

    manufacturer: Final = "Weider"
    model: Final = "WT16"

    def __init__(self, unit: Any) -> None:
        self.unit = unit
        self.measurements = Measurements(unit)
        self.settings = Settings(unit)
        self.digital_inputs = DigitalInputs(unit)

    async def async_update(self) -> None:
        """Refresh every component."""
        for component in (self.measurements, self.settings, self.digital_inputs):
            await component.async_update()

