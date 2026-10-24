"""Binary sensors for Weider WT16."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import WeiderConfigEntry, WeiderCoordinator
from .entity import WeiderEntity, is_supported


def _input(key: str, device_class: BinarySensorDeviceClass | None = None) -> BinarySensorEntityDescription:
    """Describe a digital input; its key is the weider_modbus field name."""
    return BinarySensorEntityDescription(key=key, translation_key=key, device_class=device_class)


BINARY_SENSORS: tuple[BinarySensorEntityDescription, ...] = (
    _input("flow_switch_1"),
    _input("flow_switch_2"),
    _input("remote_fault", BinarySensorDeviceClass.PROBLEM),
    _input("compressor"),
    _input("heating_pump"),
    _input("source_pump"),
    _input("mixer_pump"),
    _input("hot_water_pump"),
    _input("four_way_valve"),
    _input("reserve_1"),
    _input("reserve_2"),
    _input("reserve_3"),
    _input("cooling_output"),
    _input("reserve_5"),
    _input("hot_water_block"),
    _input("heating_block"),
    _input("utility_block"),
    _input("sg_ready_1"),
    _input("sg_ready_2"),
    _input("reserve"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WeiderConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create binary sensors for the digital inputs this device provides."""
    coordinator = entry.runtime_data
    async_add_entities(
        WeiderBinarySensor(coordinator, description)
        for description in BINARY_SENSORS
        if is_supported(coordinator, "digital_inputs", description.key)
    )


class WeiderBinarySensor(WeiderEntity, BinarySensorEntity):
    """A WT16 digital input."""

    def __init__(
        self, coordinator: WeiderCoordinator, description: BinarySensorEntityDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return getattr(self.coordinator.device.digital_inputs, self.entity_description.key)
