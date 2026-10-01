"""Base entity for Weider WT16."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import WeiderCoordinator


class WeiderEntity(CoordinatorEntity[WeiderCoordinator]):
    """Common device identity for WT16 entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: WeiderCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer="Weider",
            model="WT16",
            name="Weider WT16",
        )

