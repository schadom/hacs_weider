"""Binary sensors for Weider WT16."""

from .vendor.weider_heatpump import BINARY_POINTS, PointInfo

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import WeiderConfigEntry
from .entity import WeiderEntity, is_supported


async def async_setup_entry(hass: HomeAssistant, entry: WeiderConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        WeiderBinarySensor(coordinator, point) for point in BINARY_POINTS
        if is_supported(coordinator, point.component, point.key)
    )


class WeiderBinarySensor(WeiderEntity, BinarySensorEntity):
    def __init__(self, coordinator, point: PointInfo) -> None:
        super().__init__(coordinator, point.key)
        self.point = point
        self._attr_translation_key = point.key
        if point.device_class:
            self._attr_device_class = BinarySensorDeviceClass(point.device_class)

    @property
    def is_on(self) -> bool | None:
        return getattr(self.coordinator.device.digital_inputs, self.point.key)

