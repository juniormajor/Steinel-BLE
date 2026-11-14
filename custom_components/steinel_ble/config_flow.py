"""Config flow for Steinel True Presence BLE."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS

from .const import DOMAIN
from .protocol import SERVICE_UUID


def _title(info: BluetoothServiceInfoBleak) -> str:
    name = info.name if info.name and info.name != info.address else None
    return name or f"Steinel {info.address}"


class SteinelConfigFlow(ConfigFlow, domain=DOMAIN):
    """Discovery via the Steinel service UUID; no connection during setup flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovery: BluetoothServiceInfoBleak | None = None
        self._candidates: dict[str, BluetoothServiceInfoBleak] = {}

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle a device found by the Bluetooth matcher."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovery = discovery_info
        self.context["title_placeholders"] = {"name": _title(discovery_info)}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm a discovered device."""
        assert self._discovery is not None
        if user_input is not None:
            return self.async_create_entry(
                title=_title(self._discovery),
                data={CONF_ADDRESS: self._discovery.address},
            )
        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": _title(self._discovery)},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick one of the Steinel devices currently seen by any adapter or proxy."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=_title(self._candidates[address]), data={CONF_ADDRESS: address}
            )

        current = self._async_current_ids(include_ignore=False)
        for info in async_discovered_service_info(self.hass, connectable=True):
            if info.address in current or SERVICE_UUID not in [
                u.lower() for u in info.service_uuids
            ]:
                continue
            self._candidates[info.address] = info
        if not self._candidates:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(
                        {
                            addr: f"{_title(info)} ({addr})"
                            for addr, info in self._candidates.items()
                        }
                    )
                }
            ),
        )
