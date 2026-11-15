"""Delay for the sensor initialisation."""

from __future__ import annotations

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import protocol as p
from .coordinator import SteinelConfigEntry
from .entity import SteinelEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SteinelConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([InitDelayNumber(entry.runtime_data)])


class InitDelayNumber(SteinelEntity, RestoreNumber):
    """Delay before "Init sensor" starts, kept in Home Assistant only."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_native_min_value = 0
    _attr_native_max_value = p.INIT_SENSOR_MAX_DELAY // 60
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "init_sensor_delay")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_number_data()
        if last and last.native_value is not None:
            self.coordinator.data.init_delay_minutes = int(last.native_value)

    @property
    def native_value(self) -> float:
        return self.coordinator.data.init_delay_minutes

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.data.init_delay_minutes = int(value)
        self.async_write_ha_state()
