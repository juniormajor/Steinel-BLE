"""Config flow and setup tests (no real Bluetooth)."""

from unittest.mock import AsyncMock, patch

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from homeassistant import config_entries
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.const import CONF_ADDRESS
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.steinel_ble import protocol as p
from custom_components.steinel_ble.const import DOMAIN

ADDRESS = "F0:FC:0F:B5:A8:82"
DEVICE = BLEDevice(ADDRESS, None, None)
INFO = BluetoothServiceInfoBleak(
    name=ADDRESS,
    address=ADDRESS,
    rssi=-80,
    manufacturer_data={},
    service_data={},
    service_uuids=[p.SERVICE_UUID],
    source="proxy",
    device=DEVICE,
    advertisement=AdvertisementData(
        local_name=None, manufacturer_data={}, service_data={},
        service_uuids=[p.SERVICE_UUID], tx_power=None, rssi=-80, platform_data=(),
    ),
    connectable=True,
    time=0,
    tx_power=None,
)

READ_RESULT = {
    "info": p.parse_device_info(bytes.fromhex("a61b0500010000030102 05".replace(" ", ""))),
    "versions": p.parse_extended_info(
        bytes.fromhex(
            "00 01 0c 02 02 00 05 00 00 00 00 00 00 00 00 02 07 01 01 00 00 00 00 00"
            " 01 01 0c 02 01 00 08 00 00 00 00 00 00 00 00 02 07 00 00 00 00 00 00 00"
            " 02 01 0c 03 02 00 01 00 0c 00 00 00 00 00 00 02 07 01 01 00 00 00 00 00".replace(" ", "")
        )
    ),
    "params": {0x0517: b"\x01", 0x0518: b"\x00"},
    "name": "knx-og-bu",
}


async def test_bluetooth_discovery_creates_entry(hass):
    with patch("custom_components.steinel_ble.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_BLUETOOTH}, data=INFO
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "bluetooth_confirm"
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_ADDRESS: ADDRESS}


async def test_setup_creates_entities_and_sets_led(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ADDRESS, data={CONF_ADDRESS: ADDRESS}, title="knx-og-bu")
    entry.add_to_hass(hass)
    with (
        patch("custom_components.steinel_ble.bluetooth.async_ble_device_from_address", return_value=DEVICE),
        patch("custom_components.steinel_ble.bluetooth.async_register_callback", return_value=lambda: None),
        patch("custom_components.steinel_ble.coordinator.bluetooth.async_address_present", return_value=True),
        patch("custom_components.steinel_ble.device.SteinelDevice.read_all", AsyncMock(return_value=READ_RESULT)),
        patch("custom_components.steinel_ble.device.SteinelDevice.set_parameter", AsyncMock()) as set_param,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        states = {s.entity_id: s.state for s in hass.states.async_all()}
        fw = [v for k, v in states.items() if k.startswith("sensor.") and "firmware" in k]
        assert sorted(fw) == ["1.8", "2.1.12 | 1", "2.5 | 1"]
        led = [k for k in states if k.startswith("switch.") and "status_led" in k][0]
        assert states[led] == "on"  # 0x0518 = 0 -> LED not disabled
        noise = [k for k in states if k.startswith("switch.") and "noise" in k][0]
        assert states[noise] == "on"

        await hass.services.async_call("switch", "turn_off", {"entity_id": led}, blocking=True)
        set_param.assert_awaited_with(0x0518, b"\x01")

        assert await hass.config_entries.async_unload(entry.entry_id)
