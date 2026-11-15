"""On-demand BLE connection to one Steinel True Presence device."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import contextlib
import logging

from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from . import protocol as p
from .const import CONNECT_ATTEMPTS, IDLE_DISCONNECT, RESPONSE_TIMEOUT

_LOGGER = logging.getLogger(__name__)

GAP_DEVICE_NAME_UUID = "00002a00-0000-1000-8000-00805f9b34fb"


class SteinelDevice:
    """Request/response access to a Steinel device.

    The connection is opened per request and closed after a short idle time, so
    the Bluetooth proxy slot is only held while the device is actually used.
    """

    def __init__(self, ble_device: BLEDevice, name: str) -> None:
        self._ble_device = ble_device
        self._name = name
        self._client: BleakClientWithServiceCache | None = None
        self._lock = asyncio.Lock()
        self._assembler = p.FrameAssembler()
        self._waiters: dict[int, asyncio.Future[bytes]] = {}
        self._disconnect_timer: asyncio.TimerHandle | None = None
        self._live_callback: Callable[[p.LiveValues], None] | None = None
        self._live_until: float = 0.0

    def set_ble_device(self, ble_device: BLEDevice) -> None:
        """Use the freshest BLEDevice (path through the best proxy)."""
        self._ble_device = ble_device

    @property
    def address(self) -> str:
        return self._ble_device.address

    # --- connection ---------------------------------------------------------

    async def _ensure_connected(self) -> BleakClientWithServiceCache:
        if self._client is not None and self._client.is_connected:
            return self._client
        self._assembler = p.FrameAssembler()
        client = await establish_connection(
            BleakClientWithServiceCache,
            self._ble_device,
            self._name,
            disconnected_callback=self._on_disconnected,
            max_attempts=CONNECT_ATTEMPTS,
        )
        await client.start_notify(p.NOTIFY_CHAR_UUID, self._on_notify)
        self._client = client
        _LOGGER.debug("%s: connected via %s", self._name, self._ble_device.details)
        return client

    def _on_disconnected(self, _client: object) -> None:
        _LOGGER.debug("%s: disconnected", self._name)
        self._client = None
        for fut in self._waiters.values():
            if not fut.done():
                fut.set_exception(BleakError("disconnected"))
        self._waiters.clear()

    def _schedule_disconnect(self, delay: float = IDLE_DISCONNECT) -> None:
        if self._disconnect_timer:
            self._disconnect_timer.cancel()
        loop = asyncio.get_running_loop()
        self._disconnect_timer = loop.call_later(
            delay, lambda: asyncio.ensure_future(self.disconnect())
        )

    async def disconnect(self) -> None:
        """Close the connection (idle timer or shutdown)."""
        if self._disconnect_timer:
            self._disconnect_timer.cancel()
            self._disconnect_timer = None
        if self._live_until and asyncio.get_running_loop().time() < self._live_until:
            # live session still running, keep the connection
            self._schedule_disconnect(self._live_until - asyncio.get_running_loop().time())
            return
        self._live_until = 0.0
        client, self._client = self._client, None
        if client is not None:
            with contextlib.suppress(BleakError, EOFError):
                await client.disconnect()

    # --- notifications -------------------------------------------------------

    def _on_notify(self, _sender: object, data: bytearray) -> None:
        try:
            payloads = self._assembler.feed(bytes(data))
        except p.ProtocolError as err:
            _LOGGER.warning("%s: bad frame: %s", self._name, err)
            self._assembler = p.FrameAssembler()
            return
        for payload in payloads:
            cmd = payload[0]
            if cmd == p.CMD_LIVE_TELEGRAM:
                if self._live_callback:
                    self._live_callback(p.parse_live_telegram(payload[1:]))
                continue
            fut = self._waiters.pop(cmd, None)
            if fut and not fut.done():
                fut.set_result(payload)
            else:
                _LOGGER.debug("%s: unsolicited frame %s", self._name, payload.hex())

    # --- requests -----------------------------------------------------------

    async def _request(self, payload: bytes) -> bytes:
        """Send one request and return the data of the response (status checked)."""
        client = await self._ensure_connected()
        cmd = payload[0]
        fut: asyncio.Future[bytes] = asyncio.get_running_loop().create_future()
        self._waiters[cmd] = fut
        await client.write_gatt_char(p.WRITE_CHAR_UUID, p.build_frame(payload), response=False)
        try:
            response = await asyncio.wait_for(fut, RESPONSE_TIMEOUT)
        finally:
            self._waiters.pop(cmd, None)
        return p.check_status(response)

    async def read_all(self) -> dict:
        """Read device info, firmware versions and the app parameters."""
        async with self._lock:
            try:
                info = p.parse_device_info(await self._request(bytes([p.CMD_DEVICE_INFO])))
                versions = p.parse_extended_info(
                    await self._request(bytes([p.CMD_EXTENDED_INFO, 0x01, 0x02]))
                )
                name = None
                with contextlib.suppress(BleakError):
                    raw = await self._client.read_gatt_char(GAP_DEVICE_NAME_UUID)
                    name = bytes(raw).decode("utf-8", "replace").strip("\x00") or None
                params = p.parse_parameters(
                    await self._request(
                        p.get_parameters_request(
                            p.PARAM_KEEP_NOISE_FILTER, p.PARAM_DISABLE_STATUS_LED
                        )
                    )
                )
                knx_programming = None
                try:
                    knx_programming = p.parse_knx_programming(
                        await self._request(p.knx_programming_state_request())
                    )
                except (p.ProtocolError, TimeoutError) as err:
                    _LOGGER.debug("%s: KNX programming mode not readable: %s", self._name, err)
            finally:
                self._schedule_disconnect()
        return {
            "info": info,
            "versions": versions,
            "params": params,
            "name": name,
            "knx_programming": knx_programming,
        }

    async def set_parameter(self, param_id: int, value: bytes) -> None:
        """Set a parameter and persist it, like the app does."""
        async with self._lock:
            try:
                await self._request(p.set_parameter_request(param_id, value))
                await self._request(p.persist_request())
            finally:
                self._schedule_disconnect()

    async def set_knx_programming(self, enable: bool) -> bool:
        """Switch the KNX programming mode and read the resulting state."""
        async with self._lock:
            try:
                await self._request(p.knx_programming_request(enable))
                return p.parse_knx_programming(
                    await self._request(p.knx_programming_state_request())
                )
            finally:
                self._schedule_disconnect()

    async def start_live_session(
        self, seconds: float, callback: Callable[[p.LiveValues], None]
    ) -> None:
        """Stream live values for a limited time, then disconnect."""
        async with self._lock:
            self._live_callback = callback
            self._live_until = asyncio.get_running_loop().time() + seconds
            try:
                await self._request(p.live_values_request(True))
            finally:
                self._schedule_disconnect(seconds)
