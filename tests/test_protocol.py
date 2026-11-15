"""Tests for the protocol module with frames captured from real devices (2026-11-14)."""

import importlib.util
import pathlib
import sys

import pytest

_PATH = pathlib.Path(__file__).parents[1] / "custom_components" / "steinel_ble" / "protocol.py"
_spec = importlib.util.spec_from_file_location("steinel_protocol", _PATH)
p = importlib.util.module_from_spec(_spec)
sys.modules["steinel_protocol"] = p
_spec.loader.exec_module(p)


@pytest.mark.parametrize(
    ("payload", "frame"),
    [
        ("e0", "04e0b23100"),
        ("e40102", "06e401028e7e00"),
        ("0217051805", "08021705180548ce00"),
        ("0118050101", "0801180501011b0d00"),
        ("0118050100", "0501180501033a1d00"),
        ("03a55a55aa", "0803a55a55aaca3500"),
    ],
)
def test_build_frame_matches_capture(payload, frame):
    assert p.build_frame(bytes.fromhex(payload)).hex() == frame
    assert p.parse_frame(bytes.fromhex(frame)) == bytes.fromhex(payload)


def test_crc_check_value():
    assert p.crc16(b"123456789") == 0xE5CC


def test_crc_mismatch_raises():
    with pytest.raises(p.ProtocolError):
        p.parse_frame(bytes.fromhex("04e0b23200"))


def test_assembler_split_notifications():
    frame = p.build_frame(bytes.fromhex("0200170501011805010" + "0"))
    asm = p.FrameAssembler()
    assert asm.feed(frame[:5]) == []
    assert asm.feed(frame[5:]) == [bytes.fromhex("02001705010118050100")]


def test_parse_parameters():
    data = p.check_status(bytes.fromhex("02001705010118050100"))
    params = p.parse_parameters(data)
    assert params == {0x0517: b"\x01", 0x0518: b"\x00"}


def test_error_status():
    with pytest.raises(p.ProtocolError, match="invalid parameter"):
        p.check_status(bytes.fromhex("0202"))


def test_device_info():
    data = p.check_status(bytes.fromhex("e000a61b0500010000030102 05".replace(" ", "")))
    assert p.parse_device_info(data).product_number == 7078




def test_extended_info_buero():
    payload = bytes.fromhex(
        "e400 00 01 0c 02 02 00 05 00 00 00 00 00 00 00 00 02 07 01 01 00 00 00 00 00"
        " 01 01 0c 02 01 00 08 00 00 00 00 00 00 00 00 02 07 00 00 00 00 00 00 00"
        " 02 01 0c 03 02 00 01 00 0c 00 00 00 00 00 00 02 07 01 01 00 00 00 00 00".replace(" ", "")
    )
    comps = p.parse_extended_info(p.check_status(payload))
    assert [c.display() for c in comps] == ["2.5 | 1", "1.8", "2.1.12 | 1"]


def test_live_telegram():
    payload = bytes.fromhex(
        "0709040 16c060002021d0004026c0905027701060 2be0207022b000804418101 00".replace(" ", "")
    )
    values = p.parse_live_telegram(payload[1:])
    assert values.presence == "presence"
    assert values.distance == 0x066C
    assert values.direction == 0
    assert values.brightness == 29
    assert values.temperature == pytest.approx(24.12)
    assert values.humidity == pytest.approx(37.5)
    assert values.co2 == 702
    assert values.voc == 43
    assert values.pressure == pytest.approx(986.25)


def test_set_parameter_request():
    assert p.set_parameter_request(0x0518, b"\x01").hex() == "0118050101"
    assert p.get_parameters_request(0x0517, 0x0518).hex() == "0217051805"
    assert p.persist_request().hex() == "03a55a55aa"


def test_knx_programming_requests():
    assert p.knx_programming_request(True) == bytes.fromhex("0c01")
    assert p.knx_programming_request(False) == bytes.fromhex("0c00")
    assert p.knx_programming_state_request() == bytes.fromhex("0d")
    assert p.parse_knx_programming(b"\x01") is True
    assert p.parse_knx_programming(b"\x00") is False
    assert p.parse_knx_programming(b"") is False


def test_init_sensor_requests():
    assert p.init_sensor_request() == bytes.fromhex("16000f0400000000")
    assert p.init_sensor_request(90) == bytes.fromhex("16000f045a000000")
    with pytest.raises(ValueError):
        p.init_sensor_request(-1)
