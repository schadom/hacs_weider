"""Sensors for Weider heat pumps."""

from collections.abc import Callable
from dataclasses import dataclass

from weider_modbus import WeiderWT16, clean_error_text, plausible_temperature

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfTemperature, UnitOfTime, UnitOfVolumeFlowRate
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .coordinator import WeiderConfigEntry, WeiderCoordinator
from .entity import WeiderEntity

NO_ERROR = "none"

# SG Ready operating states (Betriebszustände), as returned by weider_modbus.
SG_READY_OPTIONS = ["bz1_utility_block", "bz2_normal", "bz3_increased", "bz4_start"]


@dataclass(frozen=True, kw_only=True)
class WeiderSensorEntityDescription(SensorEntityDescription):
    """Describes a WT16 sensor."""

    value_fn: Callable[[WeiderWT16], StateType]
    # Whether this device provides what the sensor needs.
    supported_fn: Callable[[WeiderWT16], bool]


def _provides(component: str, *fields: str) -> Callable[[WeiderWT16], bool]:
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


def _active_error(device: WeiderWT16) -> str | None:
    """Return the active error text, or NO_ERROR if the device reports none."""
    value = device.measurements.active_error
    if value is None:
        return None
    return clean_error_text(value) or NO_ERROR


def _sg_ready_mode(device: WeiderWT16) -> str | None:
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
        return self.entity_description.value_fn(self.coordinator.device)
