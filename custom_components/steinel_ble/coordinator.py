"""Coordinator: reads settings and firmware on demand, no permanent connection."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import logging

from bleak.exc import BleakError

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from . import protocol as p
from .const import DOMAIN, LIVE_SESSION_SECONDS, UPDATE_INTERVAL
from .device import SteinelDevice

_LOGGER = logging.getLogger(__name__)

BLE_ERRORS = (BleakError, TimeoutError, asyncio.TimeoutError, p.ProtocolError)


@dataclass
class SteinelData:
    product_number: int | None = None
    ble_name: str | None = None
    versions: list[p.ComponentVersion] = field(default_factory=list)
    params: dict[int, bytes] = field(default_factory=dict)
    live: p.LiveValues = field(default_factory=p.LiveValues)
    live_active: bool = False


type SteinelConfigEntry = ConfigEntry[SteinelCoordinator]


class SteinelCoordinator(DataUpdateCoordinator[SteinelData]):
    """Holds the last read state of one device."""

    config_entry: SteinelConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: SteinelConfigEntry, device: SteinelDevice
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {device.address}",
            update_interval=UPDATE_INTERVAL,
        )
        self.device = device
        self.data = SteinelData()

    @property
    def present(self) -> bool:
        """The device is in range of a connectable scanner (no connection needed)."""
        return bluetooth.async_address_present(self.hass, self.device.address, connectable=True)

    async def _async_update_data(self) -> SteinelData:
        data = self.data or SteinelData()
        try:
            result = await self.device.read_all()
        except BLE_ERRORS as err:
            raise UpdateFailed(f"Reading {self.device.address} failed: {err}") from err
        data.product_number = result["info"].product_number
        data.versions = result["versions"]
        data.ble_name = result["name"]
        data.params.update(result["params"])
        return data

    async def async_set_flag(self, param_id: int, value: bool) -> None:
        """Set a one-byte flag parameter and read it back."""
        try:
            await self.device.set_parameter(param_id, b"\x01" if value else b"\x00")
        except BLE_ERRORS as err:
            raise HomeAssistantError(f"Setting parameter 0x{param_id:04x} failed: {err}") from err
        await self.async_request_refresh()

    async def async_start_live(self, seconds: float = LIVE_SESSION_SECONDS) -> None:
        """Stream live values for ``seconds``, then the connection is closed."""

        @callback
        def _on_live(values: p.LiveValues) -> None:
            self.data.live = values
            self.data.live_active = True
            self.async_set_updated_data(self.data)

        @callback
        def _end(_now=None) -> None:
            self.data.live_active = False
            self.async_set_updated_data(self.data)

        try:
            await self.device.start_live_session(seconds, _on_live)
        except BLE_ERRORS as err:
            raise HomeAssistantError(f"Live values failed: {err}") from err
        self.hass.loop.call_later(seconds, _end)
