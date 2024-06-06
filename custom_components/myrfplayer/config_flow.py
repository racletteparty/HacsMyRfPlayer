"""Config flow for MyRfPlayer integration."""

import copy
import os
from typing import Any, cast

import serial
import voluptuous as vol

from custom_components.myrfplayer.device_profiles import async_get_profile_registry
from custom_components.myrfplayer.helpers import build_device_id_from_device_info, get_device_id_string_from_identifiers
from custom_components.myrfplayer.rfplayerlib import DEVICE_PROTOCOLS, RECEIVER_MODES, SIMULATOR_PORT
from custom_components.myrfplayer.rfplayerlib.device import RfDeviceId
from homeassistant.config_entries import HANDLERS, ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_ADDRESS, CONF_DEVICE, CONF_DEVICES, CONF_PROFILE_NAME, CONF_PROTOCOL
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv, device_registry as dr

from .const import (
    CONF_ADD_DEVICE,
    CONF_AUTOMATIC_ADD,
    CONF_DEVICE_SIMULATOR,
    CONF_INIT_COMMANDS,
    CONF_RECEIVER_PROTOCOLS,
    CONF_RECONNECT_INTERVAL,
    CONF_REDIRECT_ADDRESS,
    DEFAULT_RECEIVER_PROTOCOLS,
    DEFAULT_RECONNECT_INTERVAL,
    DOMAIN,
)

SELECT_DEVICE_EXCLUSION = "select_device"
UPDATE_DEVICES_EXCLUSION = "update_devices"


@HANDLERS.register(DOMAIN)
class RfplayerConfigFlow(ConfigFlow):
    """Handle a rfplayer config flow."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Config flow started from UI."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        schema_errors: dict[str, Any] = {}

        if user_input is not None:
            if user_input.get(CONF_DEVICE):
                device_port = await self.hass.async_add_executor_job(get_serial_by_id, user_input[CONF_DEVICE])
            elif user_input.get(CONF_DEVICE_SIMULATOR):
                device_port = SIMULATOR_PORT
            else:
                schema_errors.update({CONF_DEVICE: "device_missing"})

            if not schema_errors:
                entry_data = {
                    CONF_DEVICE: device_port,
                    CONF_AUTOMATIC_ADD: True,
                    CONF_RECONNECT_INTERVAL: DEFAULT_RECONNECT_INTERVAL,
                    CONF_RECEIVER_PROTOCOLS: DEFAULT_RECEIVER_PROTOCOLS,
                    CONF_INIT_COMMANDS: None,
                    CONF_DEVICES: {},
                    CONF_REDIRECT_ADDRESS: {},
                }
                return self.async_create_entry(title=device_port, data=entry_data)

        ports = await self.hass.async_add_executor_job(serial.tools.list_ports.comports)
        list_of_ports = {}
        for port in ports:
            list_of_ports[port.device] = f"{port}, s/n: {port.serial_number or 'n/a'}" + (
                f" - {port.manufacturer}" if port.manufacturer else ""
            )

        data_schema = {
            vol.Exclusive(CONF_DEVICE, group_of_exclusion=SELECT_DEVICE_EXCLUSION): vol.In(list_of_ports),
            vol.Exclusive(CONF_DEVICE_SIMULATOR, group_of_exclusion=SELECT_DEVICE_EXCLUSION): bool,
        }
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(data_schema),
            errors=schema_errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Define the config flow to handle options."""
        return RfPlayerOptionsFlowHandler(config_entry)


class RfPlayerOptionsFlowHandler(OptionsFlow):
    """Handle a RFPLayer options flow."""

    device_registry: dr.DeviceRegistry
    device_entries: list[dr.DeviceEntry]

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize."""
        self.config_entry = config_entry
        self.selected_device_id_string: str | None = None
        self.selected_device_info: dict[str, Any] = {}
        self.selected_device_profile: str | None = None

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage the options."""
        return await self.async_step_gateway_options(user_input)

    async def async_step_gateway_options(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Prompt for gateway options."""
        schema_errors: dict[str, Any] = {}

        if user_input is not None:
            global_options = {
                CONF_AUTOMATIC_ADD: user_input[CONF_AUTOMATIC_ADD],
                CONF_RECONNECT_INTERVAL: user_input[CONF_RECONNECT_INTERVAL],
                CONF_RECEIVER_PROTOCOLS: user_input[CONF_RECEIVER_PROTOCOLS] or None,
                CONF_INIT_COMMANDS: user_input.get(CONF_INIT_COMMANDS, None),
            }

            self.update_config_data(global_options=global_options)

            if CONF_DEVICE in user_input:
                entry_id = user_input[CONF_DEVICE]
                entry = self.device_registry.async_get(entry_id)
                if entry:
                    self.selected_device_id_string = get_device_id_string_from_identifiers(entry.identifiers)
                    self.selected_device_info = self.config_entry.data[CONF_DEVICES][self.selected_device_id_string]
                    return await self.async_step_rf_device_options()

                schema_errors.update({CONF_DEVICE: "device_missing"})

            if user_input.get(CONF_ADD_DEVICE, False):
                return await self.async_step_add_rf_device()

            return self.async_create_entry(title="", data={})

        device_registry = dr.async_get(self.hass)
        device_entries = dr.async_entries_for_config_entry(device_registry, self.config_entry.entry_id)
        self.device_registry = device_registry
        self.device_entries = device_entries

        configure_devices = {
            entry.id: entry.name_by_user if entry.name_by_user else entry.name for entry in device_entries
        }

        options = {
            vol.Required(
                CONF_AUTOMATIC_ADD,
                default=True,
            ): bool,
            vol.Required(
                CONF_RECONNECT_INTERVAL,
                default=DEFAULT_RECONNECT_INTERVAL,
            ): int,
            vol.Required(
                CONF_RECEIVER_PROTOCOLS,
                default=["*"],
            ): cv.multi_select(RECEIVER_MODES),
            vol.Optional(
                CONF_INIT_COMMANDS,
            ): str,
            vol.Exclusive(CONF_ADD_DEVICE, group_of_exclusion=UPDATE_DEVICES_EXCLUSION): bool,
            vol.Exclusive(CONF_DEVICE, group_of_exclusion=UPDATE_DEVICES_EXCLUSION): vol.In(configure_devices),
        }

        return self.async_show_form(step_id="gateway_options", data_schema=vol.Schema(options), errors=schema_errors)

    async def async_step_rf_device_options(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage RF device options."""

        if user_input is not None:
            # Existing device
            assert self.selected_device_id_string
            id_string = self.selected_device_id_string

            devices: dict[str, dict[str, Any]] = {id_string: user_input}
            devices[id_string].setdefault(CONF_REDIRECT_ADDRESS, None)

            self.update_config_data(devices=devices)

            return self.async_create_entry(title="", data={})

        option_schema = {
            vol.Optional(CONF_REDIRECT_ADDRESS): str,
        }

        return self.async_show_form(
            step_id="rf_device_options",
            data_schema=vol.Schema(option_schema),
        )

    async def async_step_add_rf_device(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Add manuall a RF device."""

        if user_input is not None:
            # New device
            id_string = RfDeviceId(protocol=user_input[CONF_PROTOCOL], address=user_input[CONF_ADDRESS]).id_string

            device_info = user_input.copy()
            device_info[CONF_REDIRECT_ADDRESS] = None

            self.update_config_data(devices={id_string: device_info})

            return self.async_create_entry(title="", data={})

        data = self.config_entry.data
        profile_registry = await async_get_profile_registry(self.hass)

        # New device
        option_schema = {
            vol.Required(CONF_PROTOCOL, default=data.get(CONF_PROTOCOL)): vol.In(DEVICE_PROTOCOLS),
            vol.Required(CONF_ADDRESS, default=data.get(CONF_ADDRESS)): str,
            vol.Required(CONF_PROFILE_NAME, default=data.get(CONF_PROFILE_NAME)): vol.In(
                profile_registry.get_profile_names()
            ),
        }

        return self.async_show_form(
            step_id="add_rf_device",
            data_schema=vol.Schema(option_schema),
        )

    @callback
    def update_config_data(
        self,
        *,
        global_options: dict[str, Any] | None = None,
        devices: dict[str, Any] | None = None,
    ) -> None:
        """Update data in ConfigEntry."""
        entry_data = self.config_entry.data.copy()
        entry_data[CONF_DEVICES] = cast(dict[str, dict], copy.deepcopy(self.config_entry.data[CONF_DEVICES]))
        if global_options:
            entry_data.update(global_options)
        if devices:
            for id_string, device_options in devices.items():
                entry_data[CONF_DEVICES].setdefault(id_string, {}).update(device_options)

            entry_data[CONF_REDIRECT_ADDRESS].clear()
            for id_string, device_info in entry_data[CONF_DEVICES].items():
                if device_info.get(CONF_REDIRECT_ADDRESS):
                    redirect_device_info = device_info.copy()
                    redirect_device_info[CONF_ADDRESS] = device_info[CONF_REDIRECT_ADDRESS]
                    redirect_id_string = build_device_id_from_device_info(redirect_device_info).id_string
                    entry_data[CONF_REDIRECT_ADDRESS][redirect_id_string] = id_string
        self.hass.config_entries.async_update_entry(self.config_entry, data=entry_data)
        self.hass.async_create_task(self.hass.config_entries.async_reload(self.config_entry.entry_id))


def get_serial_by_id(dev_path: str) -> str:
    """Return a /dev/serial/by-id match for given device if available."""
    by_id = "/dev/serial/by-id"
    if not os.path.isdir(by_id):
        return dev_path

    for path in (entry.path for entry in os.scandir(by_id) if entry.is_symlink()):
        if os.path.realpath(path) == dev_path:
            return path
    return dev_path
