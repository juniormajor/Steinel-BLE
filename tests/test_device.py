"""SteinelDevice against a fake GATT client that answers like a real device."""

import asyncio
from unittest.mock import patch

from bleak.backends.device import BLEDevice

from custom_components.steinel_ble import protocol as p
from custom_components.steinel_ble.device import SteinelDevice

# Responses captured from knx-og-bu on 2026-11-14 (payloads without CRC).
RESPONSES = {
    0xE0: "e000a61b05000100000301 0205",
    0xE4: "e40000010c0202000500000000000000000207010100000000"
    "0001010c0201000800000000000000000207000000000000"
    "0002010c03020001000c000000000000020701010000000000",
    0x02: "02001705010118050100",
    0x01: "0100",
    0x03: "0300",
    # KNX programming mode: shape derived from the app code, verified on the device.
    0x0C: "0c00",
    0x0D: "0d0000",
}


class FakeClient:
    def __init__(self):
        self.is_connected = True
        self.written = []
        self._cb = None

    async def start_notify(self, _uuid, cb):
        self._cb = cb

    async def read_gatt_char(self, _uuid):
        return bytearray(b"knx-og-bu")

    async def write_gatt_char(self, _uuid, data, response=False):
        payload = p.parse_frame(bytes(data))
        self.written.append(payload.hex())
        frame = p.build_frame(bytes.fromhex(RESPONSES[payload[0]].replace(" ", "")))
        loop = asyncio.get_running_loop()
        # deliver in MTU-sized chunks like the proxy does
        for i in range(0, len(frame), 20):
            loop.call_soon(self._cb, None, bytearray(frame[i : i + 20]))

    async def disconnect(self):
        self.is_connected = False


async def test_read_all_and_set():
    fake = FakeClient()

    async def _connect(*_args, **_kwargs):
        return fake

    with patch("custom_components.steinel_ble.device.establish_connection", _connect):
        dev = SteinelDevice(BLEDevice("F0:FC:0F:B5:A8:82", None, None), "test")
        result = await dev.read_all()
        assert result["info"].product_number == 7078
        assert [c.display() for c in result["versions"]] == ["2.5 | 1", "1.8", "2.1.12 | 1"]
        assert result["params"] == {0x0517: b"\x01", 0x0518: b"\x00"}
        assert result["name"] == "knx-og-bu"
        assert result["knx_programming"] is False
        await dev.set_parameter(0x0518, b"\x01")
        assert fake.written[-2:] == ["0118050101", "03a55a55aa"]
        await asyncio.sleep(2.5)  # idle disconnect
        assert fake.is_connected is False


async def test_knx_programming():
    fake = FakeClient()

    async def _connect(*_args, **_kwargs):
        return fake

    with patch("custom_components.steinel_ble.device.establish_connection", _connect):
        dev = SteinelDevice(BLEDevice("F0:FC:0F:B5:A8:82", None, None), "test")
        RESPONSES[0x0D] = "0d0001"
        try:
            assert await dev.set_knx_programming(True) is True
        finally:
            RESPONSES[0x0D] = "0d0000"
        assert fake.written[-2:] == ["0c01", "0d"]
        await dev.disconnect()
