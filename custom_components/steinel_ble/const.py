"""Constants for the Steinel BLE integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "steinel_ble"

# Settings and firmware are read on setup, on request and once a day.
UPDATE_INTERVAL = timedelta(hours=24)

# Connection handling: connect on demand, disconnect right after the request
# so the proxy connection slot is free again (R2/R3 of C07).
CONNECT_ATTEMPTS = 3
RESPONSE_TIMEOUT = 10.0
IDLE_DISCONNECT = 2.0

LIVE_SESSION_SECONDS = 300
