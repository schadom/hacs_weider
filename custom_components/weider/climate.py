"""Temperature controls for Weider heat pumps."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from modbus_connection import ModbusError
from weider_modbus import (
    HOT_WATER_TARGET_MAX,
    HOT_WATER_TARGET_MIN,
    ROOM_TARGET_MAX,
    ROOM_TARGET_MIN,
    TARGET_STEP,
    WeiderWT16,
    plausible_temperature,
)

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACAction, HVACMode
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import WeiderConfigEntry, WeiderCoordinator
from .entity import WeiderEntity, is_supported


@dataclass(frozen=True, kw_only=True)
class ClimateDescription:
    """Describes a target-temperature control."""

    key: str
    name: str
    current_fn: Callable[[WeiderWT16], float | None]
    target_key: str
    set_fn: Callable[[WeiderWT16, float], Awaitable[None]]
    minimum: float
    maximum: float
    pump_key: str


DESCRIPTIONS = (
    ClimateDescription(
        key="hot_water_temperature",
        name="Hot water temperature",
        current_fn=lambda device: device.measurements.hot_water_temperature,
        target_key="hot_water_target_temperature",
        set_fn=lambda device, value: device.async_set_hot_water_target(value),
        minimum=HOT_WATER_TARGET_MIN,
        maximum=HOT_WATER_TARGET_MAX,
        pump_key="hot_water_pump",
    ),
    ClimateDescription(
        key="room_temperature",
        name="Room temperature",
        # Register 12 on the standard Modbus map, register 724 on a custom map.
        current_fn=lambda device: device.current_room_temperature,
        target_key="room_target_temperature",
        set_fn=lambda device, value: device.async_set_room_target(value),
        minimum=ROOM_TARGET_MIN,
        maximum=ROOM_TARGET_MAX,
        pump_key="heating_pump",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WeiderConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create controls for the targets this device provides."""
    coordinator = entry.runtime_data
    async_add_entities(
        WeiderClimate(coordinator, description) for description in DESCRIPTIONS
        if is_supported(coordinator, "settings", description.target_key)
    )


class WeiderClimate(WeiderEntity, ClimateEntity):
    """A target-temperature control matching the legacy YAML climates."""

    _attr_hvac_modes = [HVACMode.HEAT]
    _attr_hvac_mode = HVACMode.HEAT
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = TARGET_STEP

    def __init__(self, coordinator: WeiderCoordinator, description: ClimateDescription) -> None:
        super().__init__(coordinator, f"climate_{description.key}")
        self.description = description
        self._attr_translation_key = description.key
        self._attr_min_temp = description.minimum
        self._attr_max_temp = description.maximum

    @property
    def available(self) -> bool:
        """Unavailable if this device does not provide the target register."""
        return super().available and (
            self.description.target_key in self.coordinator.device.settings.resolved_fields
        )

    @property
    def current_temperature(self) -> float | None:
        return plausible_temperature(self.description.current_fn(self.coordinator.device))

    @property
    def target_temperature(self) -> float | None:
        return getattr(self.coordinator.device.settings, self.description.target_key)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return
        try:
            await self.description.set_fn(self.coordinator.device, temperature)
        except (ModbusError, OSError, TimeoutError, ValueError) as err:
            raise HomeAssistantError(f"Unable to set {self.description.name}: {err}") from err
        await self.coordinator.async_request_refresh()

    @property
    def hvac_action(self) -> HVACAction | None:
        """Heating while the compressor and this circuit's pump both run."""
        inputs = self.coordinator.device.digital_inputs
        compressor = inputs.compressor
        pump = getattr(inputs, self.description.pump_key)
        if compressor is None or pump is None:
            return None
        return HVACAction.HEATING if compressor and pump else HVACAction.IDLE
