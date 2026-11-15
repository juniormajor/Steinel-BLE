"""Steinel True Presence BLE integration.

Uses the Home Assistant Bluetooth stack (local adapters and ESPHome Bluetooth
proxies) and connects to a device only on demand.
"""

from __future__ import annotations

import logging

from homeassistant.components import bluetooth
from homeassistant.const import CONF_ADDRESS, EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady

from .coordinator import SteinelConfigEntry, SteinelCoordinator
from .device import SteinelDevice

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BUTTON, Platform.NUMBER, Platform.SENSOR, Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: SteinelConfigEntry) -> bool:
    """Set up a Steinel device from a config entry."""
    address: str = entry.data[CONF_ADDRESS]
    ble_device = bluetooth.async_ble_device_from_address(hass, address.upper(), True)
    if ble_device is None:
        raise ConfigEntryNotReady(f"Steinel device {address} is not in range of any adapter or proxy")

    device = SteinelDevice(ble_device, entry.title)
    coordinator = SteinelCoordinator(hass, entry, device)

    @callback
    def _update_ble_device(
        service_info: bluetooth.BluetoothServiceInfoBleak, _change: bluetooth.BluetoothChange
    ) -> None:
        device.set_ble_device(service_info.device)

    entry.async_on_unload(
        bluetooth.async_register_callback(
            hass,
            _update_ble_device,
            bluetooth.BluetoothCallbackMatcher(address=address.upper(), connectable=True),
            bluetooth.BluetoothScanningMode.PASSIVE,
        )
    )

    async def _on_stop(_event: Event) -> None:
        await device.disconnect()

    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _on_stop))

    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SteinelConfigEntry) -> bool:
    """Unload a config entry and close any open connection."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.device.disconnect()
    return unloaded
