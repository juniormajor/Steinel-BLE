"""Steinel True Presence BLE protocol (frame codec and parsers).

Derived from a Bluetooth HCI capture of the Steinel SmartRemote app and verified
against Multisensor True Presence KNX devices (product 7078):

* A frame is COBS encoded and terminated by 0x00.
* The decoded frame is ``payload + CRC-16/CCITT (poly 0x1021, init 0x1D0F)`` with the
  CRC in little endian.
* Request payload: ``<command> <data...>``; response payload: ``<command> <status> <data...>``.

This module has no Home Assistant dependency so it can be unit tested on its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SERVICE_UUID = "2672b000-875a-47ff-b1ef-f3f6872db917"
NOTIFY_CHAR_UUID = "2672b004-875a-47ff-b1ef-f3f6872db917"
WRITE_CHAR_UUID = "2672b005-875a-47ff-b1ef-f3f6872db917"

CMD_SET_PARAMETER = 0x01
CMD_GET_PARAMETER = 0x02
CMD_PERSIST = 0x03
CMD_LIVE_VALUES = 0x06
CMD_LIVE_TELEGRAM = 0x07
CMD_SET_KNX_PROGRAMMING = 0x0C
CMD_GET_KNX_PROGRAMMING = 0x0D
CMD_DEVICE_CONTROL = 0x16

# Device control command IDs (product specific, from the SmartRemote app).
CONTROL_INIT_SENSOR = 0x0F
INIT_SENSOR_MAX_DELAY = 24 * 3600  # seconds; limit of this integration, not of the device
CMD_DEVICE_INFO = 0xE0
CMD_EXTENDED_INFO = 0xE4

PERSIST_MAGIC = bytes.fromhex("a55a55aa")

# Parameter IDs (16 bit, little endian on the wire).
PARAM_KEEP_NOISE_FILTER = 0x0517  # app: "Sensor-Rauschfilter beibehalten", 1 = checked
PARAM_DISABLE_STATUS_LED = 0x0518  # app: "Status-LED deaktivieren", 1 = checked

STATUS_TEXT = {
    0x00: "ok",
    0x01: "invalid command",
    0x02: "invalid parameter",
    0x03: "invalid value",
    0x04: "invalid authorisation",
    0x05: "inactive KNX parameters",
    0x06: "general error",
}

# Live value sensor IDs (enum "Sensors" of the app).
LIVE_BRIGHTNESS = 0x02
LIVE_TEMPERATURE = 0x04
LIVE_HUMIDITY = 0x05
LIVE_CO2 = 0x06
LIVE_VOC = 0x07
LIVE_PRESSURE = 0x08
LIVE_TRUE_PRESENCE = 0x09

PRESENCE_STATES = {0: "no_presence", 1: "presence", 2: "initialising"}


class ProtocolError(Exception):
    """Raised for malformed frames or error status codes."""


def crc16(data: bytes, init: int = 0x1D0F, poly: int = 0x1021) -> int:
    """CRC-16/CCITT with the init value used by Steinel (0x1D0F)."""
    crc = init
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ poly) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def cobs_encode(data: bytes) -> bytes:
    """COBS encode ``data`` and append the 0x00 delimiter."""
    out = bytearray()
    block = bytearray()
    for byte in data:
        if byte == 0:
            out.append(len(block) + 1)
            out += block
            block = bytearray()
        else:
            block.append(byte)
            if len(block) == 0xFE:
                out.append(0xFF)
                out += block
                block = bytearray()
    out.append(len(block) + 1)
    out += block
    out.append(0)
    return bytes(out)


def cobs_decode(data: bytes) -> bytes:
    """Decode one COBS frame (delimiter optional)."""
    out = bytearray()
    i = 0
    while i < len(data) and data[i] != 0:
        code = data[i]
        if i + code > len(data):
            raise ProtocolError("truncated COBS frame")
        out += data[i + 1 : i + code]
        i += code
        if code < 0xFF and i < len(data) and data[i] != 0:
            out.append(0)
    return bytes(out)


def build_frame(payload: bytes) -> bytes:
    """Build a complete frame for the write characteristic."""
    return cobs_encode(payload + crc16(payload).to_bytes(2, "little"))


def parse_frame(raw: bytes) -> bytes:
    """Decode a frame and check its CRC, return the payload."""
    decoded = cobs_decode(raw)
    if len(decoded) < 3:
        raise ProtocolError(f"frame too short: {raw.hex()}")
    payload, crc = decoded[:-2], decoded[-2:]
    if crc != crc16(payload).to_bytes(2, "little"):
        raise ProtocolError(f"CRC mismatch: {raw.hex()}")
    return payload


class FrameAssembler:
    """Collects notification chunks and yields complete payloads."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, chunk: bytes) -> list[bytes]:
        """Add a notification chunk; return all payloads completed by it."""
        self._buffer += chunk
        payloads: list[bytes] = []
        while 0 in self._buffer:
            end = self._buffer.index(0)
            raw = bytes(self._buffer[: end + 1])
            del self._buffer[: end + 1]
            if len(raw) > 1:
                payloads.append(parse_frame(raw))
        return payloads


def get_parameters_request(*param_ids: int) -> bytes:
    return bytes([CMD_GET_PARAMETER]) + b"".join(p.to_bytes(2, "little") for p in param_ids)


def set_parameter_request(param_id: int, value: bytes) -> bytes:
    return bytes([CMD_SET_PARAMETER]) + param_id.to_bytes(2, "little") + bytes([len(value)]) + value


def persist_request() -> bytes:
    return bytes([CMD_PERSIST]) + PERSIST_MAGIC


def live_values_request(enable: bool = True) -> bytes:
    return bytes([CMD_LIVE_VALUES, 0x00, 0x01 if enable else 0x00])


def knx_programming_request(enable: bool) -> bytes:
    """Switch the KNX programming mode on or off (not persisted).

    Derived from the SmartRemote app (IProductPeripheral.SetKnxProgrammingMode):
    command 0x0C with one data byte, 1 = on, 0 = off. Verified on a True Presence
    KNX detector: its green KNX programming LED follows the switch.
    """
    return bytes([CMD_SET_KNX_PROGRAMMING, 1 if enable else 0])


def knx_programming_state_request() -> bytes:
    """Read the KNX programming mode (app: GetKnxProgrammingMode, command 0x0D)."""
    return bytes([CMD_GET_KNX_PROGRAMMING])


def parse_knx_programming(data: bytes) -> bool:
    """Response data of 0x0D: first byte > 0 means programming mode is on."""
    return bool(data) and data[0] > 0


def device_control_request(instance: int, command_id: int, parameter: bytes) -> bytes:
    """Send a device control command (app: SendDeviceControlCommandAsync).

    Layout for devices with type-length-value support: ``16 <instance> <command id>
    <parameter length> <parameter>``.
    """
    return bytes([CMD_DEVICE_CONTROL, instance, command_id, len(parameter)]) + parameter


def init_sensor_request(delay_seconds: int = 0) -> bytes:
    """Initialise the presence sensor, now or after ``delay_seconds``.

    The app sends control command 0x0F on instance 0 with the delay as u32 LE
    seconds; 0 means immediately ("Init Sensor"), a delay is "Init Sensor" with a
    start time. Derived from the app code, not yet verified on a device.
    """
    if not 0 <= delay_seconds <= INIT_SENSOR_MAX_DELAY:
        raise ValueError(f"delay out of range: {delay_seconds}")
    return device_control_request(0, CONTROL_INIT_SENSOR, delay_seconds.to_bytes(4, "little"))


def check_status(payload: bytes) -> bytes:
    """Return the data part of a response, raise on an error status."""
    if len(payload) < 2:
        raise ProtocolError(f"response too short: {payload.hex()}")
    status = payload[1]
    if status != 0:
        raise ProtocolError(
            f"command 0x{payload[0]:02x} failed: {STATUS_TEXT.get(status, hex(status))}"
        )
    return payload[2:]


def parse_parameters(data: bytes) -> dict[int, bytes]:
    """Parse ``<id LE> <len> <value>`` entries of a get-parameter response."""
    result: dict[int, bytes] = {}
    i = 0
    while i + 3 <= len(data):
        pid = int.from_bytes(data[i : i + 2], "little")
        length = data[i + 2]
        result[pid] = data[i + 3 : i + 3 + length]
        i += 3 + length
    return result


@dataclass
class DeviceInfo:
    """Response to command 0xE0."""

    product_number: int
    raw: bytes


def parse_device_info(data: bytes) -> DeviceInfo:
    if len(data) < 2:
        raise ProtocolError("device info too short")
    return DeviceInfo(product_number=int.from_bytes(data[:2], "little"), raw=data)


def _parse_version(field_data: bytes) -> str | None:
    """Version field: ``<count> <u16 LE> ...``, zero padded."""
    if not field_data or field_data[0] == 0:
        return None
    count = field_data[0]
    parts = [
        str(int.from_bytes(field_data[1 + 2 * n : 3 + 2 * n], "little")) for n in range(count)
    ]
    return ".".join(parts)


@dataclass
class ComponentVersion:
    index: int
    software: str | None
    hardware: str | None

    def display(self) -> str:
        text = self.software or "?"
        return f"{text} | {self.hardware}" if self.hardware else text


def parse_extended_info(data: bytes) -> list[ComponentVersion]:
    """Parse the response to ``e4 01 02``: per component ``<index> {<type> <len> <field>}``."""
    components: dict[int, ComponentVersion] = {}
    i = 0
    while i < len(data):
        index = data[i]
        i += 1
        comp = components.setdefault(index, ComponentVersion(index, None, None))
        for _ in range(2):
            if i + 2 > len(data):
                break
            vtype, length = data[i], data[i + 1]
            value = _parse_version(data[i + 2 : i + 2 + length])
            if vtype == 0x01:
                comp.software = value
            elif vtype == 0x02:
                comp.hardware = value
            i += 2 + length
    return [components[k] for k in sorted(components)]


@dataclass
class LiveValues:
    brightness: int | None = None
    temperature: float | None = None
    humidity: float | None = None
    co2: int | None = None
    voc: int | None = None
    pressure: float | None = None
    presence: str | None = None
    distance: int | None = None
    direction: int | None = None
    unknown: dict[int, bytes] = field(default_factory=dict)


def parse_live_telegram(data: bytes) -> LiveValues:
    """Parse a live telegram (command 0x07): entries ``<sensor id> <len> <value LE>``."""
    values = LiveValues()
    i = 0
    while i + 2 <= len(data):
        sid, length = data[i], data[i + 1]
        raw = data[i + 2 : i + 2 + length]
        i += 2 + length
        num = int.from_bytes(raw, "little")
        if sid == LIVE_BRIGHTNESS:
            values.brightness = num
        elif sid == LIVE_TEMPERATURE:
            values.temperature = int.from_bytes(raw, "little", signed=True) / 100
        elif sid == LIVE_HUMIDITY:
            values.humidity = num / 10
        elif sid == LIVE_CO2:
            values.co2 = num
        elif sid == LIVE_VOC:
            values.voc = num
        elif sid == LIVE_PRESSURE:
            values.pressure = num / 100
        elif sid == LIVE_TRUE_PRESENCE and len(raw) >= 4:
            values.presence = PRESENCE_STATES.get(raw[0], str(raw[0]))
            values.distance = int.from_bytes(raw[1:3], "little")
            values.direction = raw[3]
        else:
            values.unknown[sid] = raw
    return values
