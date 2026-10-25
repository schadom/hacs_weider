"""Base entity for Weider heat pumps."""

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
    """Common device identity for Weider entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: WeiderCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            # Taken from the device library, so each device class reports
            # its own controller model.
            manufacturer=coordinator.device.manufacturer,
            model=coordinator.device.model,
            name=entry.title,
        )

