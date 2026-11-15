"""Configuration switches that mirror the SmartRemote installation settings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import protocol as p
from .coordinator import SteinelConfigEntry
from .entity import SteinelEntity


@dataclass(frozen=True, kw_only=True)
class SteinelSwitchDescription(SwitchEntityDescription):
    param_id: int
    inverted: bool = False  # True: switch on = parameter 0


SWITCHES = [
    # App: "Status-LED deaktivieren" (checked = 1). The LED only lights blue while a
    # BLE connection is active. The switch shows the LED as enabled (inverted).
    SteinelSwitchDescription(
        key="status_led",
        param_id=p.PARAM_DISABLE_STATUS_LED,
        inverted=True,
        entity_category=EntityCategory.CONFIG,
    ),
    # App: "Sensor-Rauschfilter beibehalten" (checked = 1).
    SteinelSwitchDescription(
        key="keep_noise_filter",
        param_id=p.PARAM_KEEP_NOISE_FILTER,
        entity_category=EntityCategory.CONFIG,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SteinelConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SwitchEntity] = [SteinelSwitch(coordinator, d) for d in SWITCHES]
    entities.append(SteinelKnxProgrammingSwitch(coordinator))
    async_add_entities(entities)


class SteinelSwitch(SteinelEntity, SwitchEntity):
    entity_description: SteinelSwitchDescription

    def __init__(self, coordinator, description: SteinelSwitchDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        raw = self.coordinator.data.params.get(self.entity_description.param_id)
        if not raw:
            return None
        value = raw[0] != 0
        return not value if self.entity_description.inverted else value

    async def _async_set(self, on: bool) -> None:
        value = not on if self.entity_description.inverted else on
        await self.coordinator.async_set_flag(self.entity_description.param_id, value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set(False)


class SteinelKnxProgrammingSwitch(SteinelEntity, SwitchEntity):
    """KNX programming mode, like the programming button on the device.

    The state is read with every refresh; the device may leave the mode on its own
    (e.g. after ETS has assigned the physical address).
    """

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "knx_programming")

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data.knx_programming

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_knx_programming(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_knx_programming(False)
