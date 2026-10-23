"""Base entity for Weider WT16."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import WeiderCoordinator


def is_supported(coordinator: WeiderCoordinator, component: str, key: str) -> bool:
    """Return whether this device provides the field.

    The first refresh runs before entities are created and drops fields the
    device rejects, so platforms create entities for supported fields only.
    """
    return key in getattr(coordinator.device, component).resolved_fields


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
            name=entry.title,
        )

