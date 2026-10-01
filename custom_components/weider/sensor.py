"""Sensors for Weider WT16."""

from .vendor.weider_heatpump import POINTS, PointInfo

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import WeiderConfigEntry
from .entity import WeiderEntity


async def async_setup_entry(hass: HomeAssistant, entry: WeiderConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    async_add_entities(WeiderSensor(entry.runtime_data, point) for point in POINTS)


class WeiderSensor(WeiderEntity, SensorEntity):
    """A WT16 numeric or text sensor."""

    def __init__(self, coordinator, point: PointInfo) -> None:
        super().__init__(coordinator, point.key)
        self.point = point
        self._attr_name = point.name
        self._attr_native_unit_of_measurement = point.unit
        if point.device_class:
            self._attr_device_class = SensorDeviceClass(point.device_class)

    @property
    def native_value(self):
        return getattr(getattr(self.coordinator.device, self.point.component), self.point.key)

