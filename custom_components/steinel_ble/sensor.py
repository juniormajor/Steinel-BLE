"""Sensors: firmware (diagnostic) and live values of the last live session."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    LIGHT_LUX,
    PERCENTAGE,
    EntityCategory,
    UnitOfLength,
    UnitOfPressure,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant

try:  # HA 2026.11+: CONCENTRATION_PARTS_PER_* deprecated, removed in 2027.8
    from homeassistant.const import UnitOfRatio

    PPB = UnitOfRatio.PARTS_PER_BILLION
    PPM = UnitOfRatio.PARTS_PER_MILLION
except ImportError:  # older HA
    from homeassistant.const import (
        CONCENTRATION_PARTS_PER_BILLION as PPB,
        CONCENTRATION_PARTS_PER_MILLION as PPM,
    )
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import SteinelConfigEntry, SteinelData
from .entity import SteinelEntity
from .protocol import PRESENCE_STATES


@dataclass(frozen=True, kw_only=True)
class SteinelSensorDescription(SensorEntityDescription):
    value_fn: Callable[[SteinelData], Any]


def _version(index: int) -> Callable[[SteinelData], Any]:
    def _fn(data: SteinelData) -> Any:
        for comp in data.versions:
            if comp.index == index:
                return comp.display()
        return None

    return _fn


DIAGNOSTIC = [
    SteinelSensorDescription(
        key=f"firmware_{i}",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_version(i),
    )
    for i in range(3)
] + [
    SteinelSensorDescription(
        key="ble_name",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.ble_name,
    ),
]

# Live values duplicate what the KNX variant already reports on the bus, so they
# are disabled by default and only filled during a live session (button).
LIVE = [
    SteinelSensorDescription(
        key="brightness",
        device_class=SensorDeviceClass.ILLUMINANCE,
        native_unit_of_measurement=LIGHT_LUX,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.live.brightness,
    ),
    SteinelSensorDescription(
        key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda d: d.live.temperature,
    ),
    SteinelSensorDescription(
        key="humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.live.humidity,
    ),
    SteinelSensorDescription(
        key="co2",
        device_class=SensorDeviceClass.CO2,
        native_unit_of_measurement=PPM,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.live.co2,
    ),
    SteinelSensorDescription(
        key="voc",
        device_class=SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS_PARTS,
        native_unit_of_measurement=PPB,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.live.voc,
    ),
    SteinelSensorDescription(
        key="pressure",
        device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        native_unit_of_measurement=UnitOfPressure.HPA,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.live.pressure,
    ),
    SteinelSensorDescription(
        key="presence",
        device_class=SensorDeviceClass.ENUM,
        options=list(PRESENCE_STATES.values()),
        value_fn=lambda d: d.live.presence,
    ),
    SteinelSensorDescription(
        key="distance",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.MILLIMETERS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.live.distance,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SteinelConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities = [SteinelSensor(coordinator, d) for d in DIAGNOSTIC]
    entities += [SteinelSensor(coordinator, d, enabled_default=False) for d in LIVE]
    async_add_entities(entities)


class SteinelSensor(SteinelEntity, SensorEntity):
    entity_description: SteinelSensorDescription

    def __init__(self, coordinator, description, enabled_default: bool = True) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._attr_entity_registry_enabled_default = enabled_default

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)
