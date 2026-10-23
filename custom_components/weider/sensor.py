"""Sensors for Weider WT16."""

from .vendor.weider_heatpump import POINTS, PointInfo

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import WeiderConfigEntry
from .entity import WeiderEntity
from .plausibility import plausible_temperature

NO_ERROR = "none"


async def async_setup_entry(hass: HomeAssistant, entry: WeiderConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities(WeiderSensor(entry.runtime_data, point) for point in POINTS)


class WeiderSensor(WeiderEntity, SensorEntity):
    """A WT16 numeric or text sensor."""

    def __init__(self, coordinator, point: PointInfo) -> None:
        super().__init__(coordinator, point.key)
        self.point = point
        self._attr_translation_key = point.key
        self._attr_native_unit_of_measurement = point.unit
        if point.device_class:
            self._attr_device_class = SensorDeviceClass(point.device_class)

    @property
    def native_value(self):
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

