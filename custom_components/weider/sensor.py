"""Sensors for Weider WT16."""

from .vendor.weider_heatpump import POINTS, ROOM_TEMPERATURE_FIELDS, PointInfo

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import WeiderConfigEntry
from .entity import WeiderEntity, is_supported
from .plausibility import plausible_temperature

NO_ERROR = "none"


# SG Ready operating states (Betriebszustände), derived from the digital inputs.
BZ1_UTILITY_BLOCK = "bz1_utility_block"
BZ2_NORMAL = "bz2_normal"
BZ3_INCREASED = "bz3_increased"
BZ4_START = "bz4_start"
SG_READY_OPTIONS = [BZ1_UTILITY_BLOCK, BZ2_NORMAL, BZ3_INCREASED, BZ4_START]
SG_READY_MODE = PointInfo("sg_ready_mode", "SG Ready mode", "digital_inputs", device_class="enum")


async def async_setup_entry(hass: HomeAssistant, entry: WeiderConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        WeiderSensor(coordinator, point) for point in POINTS
        if is_supported(coordinator, point.component, point.key)
        or (point.key == "room_temperature" and any(
            is_supported(coordinator, "measurements", key) for key in ROOM_TEMPERATURE_FIELDS
        ))
    ]
    if all(is_supported(coordinator, "digital_inputs", key) for key in ("sg_ready_1", "sg_ready_2")):
        entities.append(WeiderSgReadyModeSensor(coordinator))
    async_add_entities(entities)


class WeiderSensor(WeiderEntity, SensorEntity):
    """A WT16 numeric or text sensor."""

    def __init__(self, coordinator, point: PointInfo) -> None:
        super().__init__(coordinator, point.key)
        self.point = point
        self._attr_translation_key = point.key
        self._attr_native_unit_of_measurement = point.unit
        if point.device_class:
            self._attr_device_class = SensorDeviceClass(point.device_class)
        if point.key != "active_error":  # the only text point; the rest are measurements
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        if self.point.key == "room_temperature":
            value = self.coordinator.device.current_room_temperature
        else:
            value = getattr(getattr(self.coordinator.device, self.point.component), self.point.key)
        if self.point.key == "active_error" and isinstance(value, str):
            return clean_error_text(value)
        if self.point.device_class == "temperature":
            return plausible_temperature(value)
        return value


def clean_error_text(value: str) -> str:
    """Remove null and space padding from the device's error text.

    The device pads the 16-register text with null characters or spaces,
    so "no error" arrives as padding only. That case reads as NO_ERROR.
    """
    text = " ".join(value.replace("\x00", " ").split())
    return text or NO_ERROR



def sg_ready_mode(utility_block: bool | None, sg_ready_1: bool | None, sg_ready_2: bool | None) -> str | None:
    """Return the SG Ready operating state for the given input states.

    The utility company block always means BZ1. Otherwise SG Ready 1 and 2
    select the state: only SG Ready 2 on is BZ3, only SG Ready 1 on is BZ4,
    and anything else is BZ2. A missing utility block reading counts as no
    block; missing SG Ready readings make the state unknown.
    """
    if utility_block:
        return BZ1_UTILITY_BLOCK
    if sg_ready_1 is None or sg_ready_2 is None:
        return None
    if sg_ready_2 and not sg_ready_1:
        return BZ3_INCREASED
    if sg_ready_1 and not sg_ready_2:
        return BZ4_START
    return BZ2_NORMAL


class WeiderSgReadyModeSensor(WeiderEntity, SensorEntity):
    """The SG Ready operating state, derived from the digital inputs."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = SG_READY_OPTIONS
    _attr_translation_key = SG_READY_MODE.key
    _attr_icon = "mdi:transmission-tower"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, SG_READY_MODE.key)

    @property
    def native_value(self) -> str | None:
        inputs = self.coordinator.device.digital_inputs
        return sg_ready_mode(inputs.utility_block, inputs.sg_ready_1, inputs.sg_ready_2)
