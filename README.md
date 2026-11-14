# Steinel True Presence BLE

Home Assistant custom integration for the Bluetooth LE interface of Steinel
**Multisensor True Presence KNX** presence detectors (product 7078). It uses the
Home Assistant Bluetooth stack, so local adapters and the ESPHome Bluetooth
proxies Home Assistant already uses are shared with all other Bluetooth
integrations.

## What it does

* Finds detectors by their advertisements (service `2672b000-875a-47ff-b1ef-f3f6872db917`).
* Connects **only on demand** and disconnects about two seconds after the last
  request, so a proxy connection slot is held for a few seconds at most.
* Reads firmware versions and the two settings the SmartRemote app offers, on setup,
  once a day and with the button *Read settings*.
* Switches: *Status LED* (app setting "Status-LED deaktivieren", inverted) and
  *Keep sensor noise filter* ("Sensor-Rauschfilter beibehalten").
* *Live values (5 min)*: streams brightness, temperature, humidity, CO2, VOC,
  air pressure, presence and distance for five minutes, then disconnects. The live
  sensors and the button are disabled by default because the KNX variant reports
  these values on the bus anyway.
* An entity is available while any adapter or proxy sees the detector; no
  permanent connection is needed.

Not (yet) supported: *Init Sensor*, *Reset*, *KNX programming mode* and firmware
updates. Their commands are not known yet; firmware updates will not be added.

## Installation

HACS → ⋮ → Custom repositories → `https://github.com/juniormajor/Steinel-BLE`,
type *Integration*. Install, restart Home Assistant; detectors in range are
discovered automatically.

Requirements: a Bluetooth adapter or an ESPHome Bluetooth proxy with
`bluetooth_proxy: active: true` in range of the detector. The detector accepts the
connection without pairing. While the SmartRemote app is connected to a detector,
requests from Home Assistant may fail.

## Protocol

Write characteristic `2672b005`, notify characteristic `2672b004`. Frames are COBS
encoded and terminated by `0x00`; the payload is followed by a CRC-16/CCITT
(poly 0x1021, init 0x1D0F, little endian). Request `<command> <data>`, response
`<command> <status> <data>`. See `custom_components/steinel_ble/protocol.py`.

| Command | Request | Meaning |
|---|---|---|
| `e0` | `e0` | device info (product number u16 LE) |
| `e4` | `e4 01 02` | software / hardware version per component |
| `02` | `02 <id LE>…` | read parameters |
| `01` | `01 <id LE> <len> <value>` | set parameter |
| `03` | `03 a5 5a 55 aa` | persist (sent after every set) |
| `06` | `06 00 01` | start live values (telegram `07` every 0.5 s) |

Parameters: `0x0517` keep noise filter (1 = on), `0x0518` disable status LED (1 = disabled).

## Development

```
pip install pytest-homeassistant-custom-component
pytest
```

## License

MIT – see [LICENSE](LICENSE). Not affiliated with or endorsed by STEINEL GmbH; the BLE protocol was analysed from own captures.
