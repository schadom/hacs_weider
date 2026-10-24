"""Temperature controls for Weider WT16."""

from dataclasses import dataclass

from modbus_connection import ModbusError

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACAction, HVACMode
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import WeiderConfigEntry
from .entity import WeiderEntity, is_supported
from .plausibility import plausible_temperature


@dataclass(frozen=True, slots=True)
class ClimateDescription:
    key: str
    name: str
    current_key: str
    target_key: str
    minimum: float
    maximum: float
    pump_key: str


DESCRIPTIONS = (
    ClimateDescription("hot_water_temperature", "Hot water temperature", "hot_water_temperature", "hot_water_target_temperature", 15, 55, "hot_water_pump"),
    ClimateDescription("room_temperature", "Room temperature", "room_temperature", "room_target_temperature", 15, 35, "heating_pump"),
)


async def async_setup_entry(hass: HomeAssistant, entry: WeiderConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
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
    _attr_target_temperature_step = 0.5

    def __init__(self, coordinator, description: ClimateDescription) -> None:
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
        device = self.coordinator.device
        if self.description.current_key == "room_temperature":
            return plausible_temperature(device.current_room_temperature)
        return plausible_temperature(getattr(device.measurements, self.description.current_key))

    @property
    def target_temperature(self) -> float | None:
        return getattr(self.coordinator.device.settings, self.description.target_key)

    async def async_set_temperature(self, **kwargs) -> None:
        temperature = kwargs.get("temperature")
        if temperature is None:
            return
        try:
            await self.coordinator.device.settings.write(self.description.target_key, temperature)
        except (ModbusError, OSError, TimeoutError) as err:
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

