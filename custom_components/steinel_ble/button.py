"""Buttons that connect only when pressed."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SteinelConfigEntry
from .entity import SteinelEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SteinelConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        [ReadSettingsButton(coordinator), LiveValuesButton(coordinator), InitSensorButton(coordinator)]
    )


class ReadSettingsButton(SteinelEntity, ButtonEntity):
    """Read firmware and settings now."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "read_settings")

    async def async_press(self) -> None:
        await self.coordinator.async_refresh()


class LiveValuesButton(SteinelEntity, ButtonEntity):
    """Stream live values for five minutes, then disconnect."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "live_values")

    async def async_press(self) -> None:
        await self.coordinator.async_start_live()


class InitSensorButton(SteinelEntity, ButtonEntity):
    """Initialise the presence sensor (app: "Init Sensor").

    Uses the delay of the number entity "Init sensor delay" (0 = immediately).
    Disabled by default: the detector re-learns its room afterwards.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "init_sensor")

    async def async_press(self) -> None:
        await self.coordinator.async_init_sensor()
