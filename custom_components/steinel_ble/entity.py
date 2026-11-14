"""Base entity for Steinel True Presence BLE."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SteinelCoordinator

PRODUCTS = {7078: "Multisensor True Presence KNX"}


class SteinelEntity(CoordinatorEntity[SteinelCoordinator]):
    """Entity that is available while the device is in Bluetooth range."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SteinelCoordinator, key: str) -> None:
        super().__init__(coordinator)
        address = coordinator.device.address
        self._attr_unique_id = f"{address}_{key}"
        self._attr_translation_key = key
        data = coordinator.data
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, address)},
            connections={(CONNECTION_BLUETOOTH, address)},
            manufacturer="Steinel",
            model=PRODUCTS.get(data.product_number or 0, f"Product {data.product_number}"),
            model_id=str(data.product_number) if data.product_number else None,
            sw_version=data.versions[0].display() if data.versions else None,
            name=coordinator.config_entry.title,
        )

    @property
    def available(self) -> bool:
        """Available while a scanner sees the device; a connection is not required."""
        return self.coordinator.present and self.coordinator.data.product_number is not None
