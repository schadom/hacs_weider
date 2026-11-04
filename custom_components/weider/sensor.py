"""Sensors for Weider heat pumps."""

from collections.abc import Callable
from dataclasses import dataclass

from weider_modbus import clean_error_text, plausible_temperature

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfEnergy,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .connection import WeiderDevice
from .const import TARGET_KEYS
from .coordinator import WeiderConfigEntry, WeiderCoordinator
from .entity import WeiderEntity

# Entities only read the coordinator's data; the coordinator does all polling.
PARALLEL_UPDATES = 0

NO_ERROR = "none"

# SG Ready operating states (Betriebszustände), as returned by weider_modbus.
SG_READY_OPTIONS = ["bz1_utility_block", "bz2_normal", "bz3_increased", "bz4_start"]
# Summer or winter operation, on the RS485 map only.
SEASON_OPTIONS = ["summer", "winter"]
# Error number the RS485 map reports when there is no active error.
NO_ERROR_CODE = -1


@dataclass(frozen=True, kw_only=True)
class WeiderSensorEntityDescription(SensorEntityDescription):
    """Describes a WT16 sensor."""

    value_fn: Callable[[WeiderDevice], StateType]
    # Whether this device provides what the sensor needs.
    supported_fn: Callable[[WeiderDevice], bool]


def _provides(component: str, *fields: str) -> Callable[[WeiderDevice], bool]:
    """Return a check that the device provides any of the given fields."""
    return lambda device: any(
        field in getattr(device, component).resolved_fields for field in fields
    )


def _temperature(
    key: str, component: str = "measurements", *, enabled_default: bool = True
) -> WeiderSensorEntityDescription:
    """Describe a temperature field, hiding the device's placeholder values."""
    return WeiderSensorEntityDescription(
        key=key,
        translation_key=key,
        entity_registry_enabled_default=enabled_default,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: plausible_temperature(getattr(getattr(device, component), key)),
        supported_fn=_provides(component, key),
    )


def _active_error(device: WeiderDevice) -> str | None:
    """Return the active error text, or NO_ERROR if the device reports none."""
    value = device.measurements.active_error
    if value is None:
        return None
    return clean_error_text(value) or NO_ERROR


def _active_error_code(device: WeiderDevice) -> str | None:
    """Return the active error number, or NO_ERROR if the device reports none."""
    code = device.measurements.active_error_code
    if code is None:
        return None
    return NO_ERROR if code == NO_ERROR_CODE else str(code)


def _season(device: WeiderDevice) -> str | None:
    winter = device.measurements.winter_mode
    return None if winter is None else SEASON_OPTIONS[winter]


def _value(component: str, key: str) -> Callable[[WeiderDevice], StateType]:
    """Return a value function for a field read as it is."""
    return lambda device: getattr(getattr(device, component), key)


def _sg_ready_mode(device: WeiderDevice) -> str | None:
    mode = device.sg_ready_mode
    return None if mode is None else mode.value


SENSORS: tuple[WeiderSensorEntityDescription, ...] = (
    _temperature("hot_water_target_temperature", "settings"),
    _temperature("room_target_temperature", "settings"),
    _temperature("hot_water_temperature"),
    # Register 12 on the standard Modbus map, register 724 on a custom map.
    WeiderSensorEntityDescription(
        key="room_temperature",
        translation_key="room_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: plausible_temperature(device.current_room_temperature),
        supported_fn=_provides("measurements", "room_temperature", "custom_map_room_temperature"),
    ),
    _temperature("flow_target_temperature"),
    _temperature("flow_temperature"),
    _temperature("outdoor_temperature"),
    _temperature("buffer_temperature"),
    _temperature("mixer_temperature"),
    # Reserve sensors are only connected on some installations, so they are
    # disabled by default. Users can enable them in Home Assistant.
    _temperature("reserve_temperature_1", enabled_default=False),
    _temperature("reserve_temperature_2", enabled_default=False),
    _temperature("reserve_temperature_3", enabled_default=False),
    _temperature("defrost_temperature"),
    _temperature("return_temperature"),
    _temperature("source_inlet_temperature"),
    _temperature("source_outlet_temperature"),
    _temperature("superheat"),
    _temperature("evaporation_temperature"),
    _temperature("condensation_temperature"),
    _temperature("evaporator_temperature"),
    _temperature("suction_gas_temperature"),
    _temperature("hot_gas_temperature"),
    WeiderSensorEntityDescription(
        key="volume_flow",
        translation_key="volume_flow",
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        native_unit_of_measurement=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
        suggested_display_precision=2,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.measurements.volume_flow,
        supported_fn=_provides("measurements", "volume_flow"),
    ),
    WeiderSensorEntityDescription(
        key="active_error",
        translation_key="active_error",
        value_fn=_active_error,
        supported_fn=_provides("measurements", "active_error"),
    ),
    WeiderSensorEntityDescription(
        key="last_pump_runtime",
        translation_key="last_pump_runtime",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.measurements.last_pump_runtime,
        supported_fn=_provides("measurements", "last_pump_runtime"),
    ),
    WeiderSensorEntityDescription(
        key="last_hot_water_runtime",
        translation_key="last_hot_water_runtime",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.measurements.last_hot_water_runtime,
        supported_fn=_provides("measurements", "last_hot_water_runtime"),
    ),
    WeiderSensorEntityDescription(
        key="mixer_position",
        translation_key="mixer_position",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.measurements.mixer_position,
        supported_fn=_provides("measurements", "mixer_position"),
    ),
    WeiderSensorEntityDescription(
        key="sg_ready_mode",
        translation_key="sg_ready_mode",
        device_class=SensorDeviceClass.ENUM,
        options=SG_READY_OPTIONS,
        icon="mdi:transmission-tower",
        value_fn=_sg_ready_mode,
        # The mode needs both SG Ready inputs.
        supported_fn=lambda device: all(
            field in device.digital_inputs.resolved_fields
            for field in ("sg_ready_1", "sg_ready_2")
        ),
    ),
    # Values on the RS485 (Modbus RTU) map only.
    _temperature("hot_water_hysteresis", "settings"),
    _temperature("heating_limit_temperature", "settings"),
    _temperature("average_outdoor_temperature"),
    _temperature("circuit_1_flow_target_temperature"),
    _temperature("circuit_1_flow_temperature"),
    WeiderSensorEntityDescription(
        key="operating_season",
        translation_key="operating_season",
        device_class=SensorDeviceClass.ENUM,
        options=SEASON_OPTIONS,
        value_fn=_season,
        supported_fn=_provides("measurements", "winter_mode"),
    ),
    WeiderSensorEntityDescription(
        key="mixer_2_position",
        translation_key="mixer_2_position",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_value("measurements", "mixer_2_position"),
        supported_fn=_provides("measurements", "mixer_2_position"),
    ),
    WeiderSensorEntityDescription(
        key="operating_hours",
        translation_key="operating_hours",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_value("measurements", "operating_hours"),
        supported_fn=_provides("measurements", "operating_hours"),
    ),
    WeiderSensorEntityDescription(
        key="heating_hours",
        translation_key="heating_hours",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_value("measurements", "heating_hours"),
        supported_fn=_provides("measurements", "heating_hours"),
    ),
    WeiderSensorEntityDescription(
        key="last_heating_runtime",
        translation_key="last_heating_runtime",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_value("measurements", "last_heating_runtime"),
        supported_fn=_provides("measurements", "last_heating_runtime"),
    ),
    WeiderSensorEntityDescription(
        key="heat_energy",
        translation_key="heat_energy",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=_value("measurements", "heat_energy"),
        supported_fn=_provides("measurements", "heat_energy"),
    ),
    WeiderSensorEntityDescription(
        key="active_error_code",
        translation_key="active_error_code",
        value_fn=_active_error_code,
        supported_fn=_provides("measurements", "active_error_code"),
    ),
    WeiderSensorEntityDescription(
        key="sg_ready_manual_mode",
        translation_key="sg_ready_manual_mode",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_value("measurements", "sg_ready_manual_mode"),
        supported_fn=_provides("measurements", "sg_ready_manual_mode"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WeiderConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create sensors for the fields this device provides."""
    coordinator = entry.runtime_data
    async_add_entities(
        WeiderSensor(coordinator, description)
        for description in SENSORS
        if description.supported_fn(coordinator.device)
    )


class WeiderSensor(WeiderEntity, SensorEntity):
    """A WT16 sensor."""

    entity_description: WeiderSensorEntityDescription

    def __init__(
        self, coordinator: WeiderCoordinator, description: WeiderSensorEntityDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType:
        if self.entity_description.key in TARGET_KEYS:
            # Show a newly written target right away, like the climate entity.
            return plausible_temperature(self.coordinator.target(self.entity_description.key))
        return self.entity_description.value_fn(self.coordinator.device)
