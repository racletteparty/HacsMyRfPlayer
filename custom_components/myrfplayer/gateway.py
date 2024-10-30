"""RfPlayer gateway."""

import asyncio
import copy
import logging
from typing import cast

import voluptuous as vol

from custom_components.myrfplayer.device_profiles import async_get_profile_registry
from custom_components.myrfplayer.helpers import build_device_info_from_event, get_device_id_string_from_identifiers
from custom_components.myrfplayer.rfplayerlib import COMMAND_PROTOCOLS, RfPlayerClient, RfPlayerException
from custom_components.myrfplayer.rfplayerlib.device import RfDeviceEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_DEVICE_ID,
    CONF_ADDRESS,
    CONF_DEVICE,
    CONF_DEVICES,
    CONF_PROFILE_NAME,
    CONF_PROTOCOL,
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.core import CoreState, Event, HassJob, HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ConfigEntryNotReady, PlatformNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import EventDeviceRegistryUpdatedData
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later

from .const import (
    ATTR_COMMAND,
    ATTR_EVENT_DATA,
    CONF_AUTOMATIC_ADD,
    CONF_INIT_COMMANDS,
    CONF_RECEIVER_PROTOCOLS,
    CONF_RECONNECT_INTERVAL,
    CONF_REDIRECT_ADDRESS,
    CONNECTION_TIMEOUT,
    DOMAIN,
    RFPLAYER_CLIENT,
    SERVICE_SEND_PAIRING_COMMAND,
    SERVICE_SEND_RAW_COMMAND,
    SERVICE_SIMULATE_EVENT,
    SIGNAL_RFPLAYER_AVAILABILITY,
    SIGNAL_RFPLAYER_EVENT,
)

_LOGGER = logging.getLogger(__name__)

SERVICE_SEND_RAW_COMMAND_SCHEMA = vol.Schema({ATTR_COMMAND: str})
SERVICE_SEND_PAIRING_COMMAND_SCHEMA = vol.Schema({CONF_PROTOCOL: vol.In(COMMAND_PROTOCOLS), CONF_ADDRESS: str})
SERVICE_SIMULATE_EVENT_SCHEMA = vol.Schema({ATTR_EVENT_DATA: dict})

JAMMING_DEVICE_ID_STRING = "JAMMING_0"
JAMMING_DEVICE_INFO = {CONF_PROTOCOL: "JAMMING", CONF_ADDRESS: "0", CONF_PROFILE_NAME: "Jamming Detector"}


class Gateway:
    """RfPlayer gateway."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        """Create a new RfPlayer gateway."""

        self.hass = hass
        self.entry = entry
        self.config = entry.data
        self.device_ids: set[str] = set()
        self.device_registry = dr.async_get(hass)
        # All RfPlayer gateways are configured by default with a Jamming detector
        self.config[CONF_DEVICES].update({JAMMING_DEVICE_ID_STRING: JAMMING_DEVICE_INFO})

    async def async_setup(self):
        """Load a RfPlayer gateway."""

        self.profile_registry = await async_get_profile_registry(self.hass)

        # Initialize library
        client = RfPlayerClient(
            event_callback=self._async_handle_receive,
            disconnect_callback=self._reconnect_gateway,
            loop=self.hass.loop,
            port=self.config[CONF_DEVICE],
            receiver_protocols=self.config[CONF_RECEIVER_PROTOCOLS],
            init_commands=self.config[CONF_INIT_COMMANDS],
        )
        self.hass.data[DOMAIN][RFPLAYER_CLIENT] = client

        await self.entry.async_create_task(self.hass, self._connect_gateway())

        self.entry.async_on_unload(
            self.hass.bus.async_listen(dr.EVENT_DEVICE_REGISTRY_UPDATED, self._updated_rf_device)
        )

        self.entry.async_on_unload(self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, lambda _: client.close()))

        self.hass.services.async_register(
            DOMAIN,
            SERVICE_SEND_RAW_COMMAND,
            self._send_raw_command,
            schema=SERVICE_SEND_RAW_COMMAND_SCHEMA,
        )
        self.hass.services.async_register(
            DOMAIN,
            SERVICE_SEND_PAIRING_COMMAND,
            self._send_pairing_command,
            schema=SERVICE_SEND_PAIRING_COMMAND_SCHEMA,
        )
        self.hass.services.async_register(
            DOMAIN,
            SERVICE_SIMULATE_EVENT,
            self._simulate_event,
            schema=SERVICE_SIMULATE_EVENT_SCHEMA,
        )

    async def async_unload(self):
        """Unload a RfPlayer gateway."""

        self.hass.services.async_remove(DOMAIN, SERVICE_SEND_RAW_COMMAND)

        await self.hass.async_add_executor_job(self._get_client().close)

    @callback
    def _async_handle_receive(self, event: RfDeviceEvent) -> None:
        """Event handler connected to the client."""

        _LOGGER.debug("Received event from %s", event.device.id_string)

        if event.id_string not in self.device_ids and self.config[CONF_AUTOMATIC_ADD]:
            self._add_rf_device(event)
            # Still send event for group events

        # Replace event address if device has redirect configuration
        if event.id_string in self.config[CONF_REDIRECT_ADDRESS]:
            redirected_id_string = self.config[CONF_REDIRECT_ADDRESS][event.id_string]
            event.device.address = self.config[CONF_DEVICES][redirected_id_string][CONF_ADDRESS]

        # Callback to HA registered components.
        async_dispatcher_send(self.hass, SIGNAL_RFPLAYER_EVENT, event)  # type: ignore[has-type]

    @callback
    def _add_rf_device(self, event: RfDeviceEvent) -> None:
        _LOGGER.info(
            "Added device %s (Proto: %s Addr: %s Model: %s)",
            event.device.id_string,
            event.device.protocol,
            event.device.address,
            event.device.model,
        )

        data = self.entry.data.copy()
        data[CONF_DEVICES] = copy.deepcopy(self.entry.data[CONF_DEVICES])
        data[CONF_DEVICES][event.device.id_string] = build_device_info_from_event(self.profile_registry, event)
        self.hass.config_entries.async_update_entry(entry=self.entry, data=data)
        self.device_ids.add(event.device.id_string)

    @callback
    def _remove_rf_device(self, id_string: str) -> None:
        data = {
            **self.entry.data,
            CONF_DEVICES: {
                device_config_id: entity_info
                for device_config_id, entity_info in self.entry.data[CONF_DEVICES].items()
                if device_config_id != id_string
            },
        }
        self.hass.config_entries.async_update_entry(entry=self.entry, data=data)
        self.device_ids.remove(id_string)

    @callback
    def _updated_rf_device(self, event: Event[EventDeviceRegistryUpdatedData]) -> None:
        if event.data["action"] != "remove":
            return
        device_entry = self.device_registry.deleted_devices[event.data[ATTR_DEVICE_ID]]
        if self.entry.entry_id not in device_entry.config_entries:
            return
        id_string = get_device_id_string_from_identifiers(device_entry.identifiers)
        if id_string:
            self._remove_rf_device(id_string)

    async def _connect_gateway(self):
        """Set up connection and hook it into HA for reconnect/shutdown."""
        _LOGGER.info("Initiating RFPlayer connection")

        client = self._get_client()
        try:
            async with asyncio.timeout(CONNECTION_TIMEOUT):
                await client.connect()

        except (
            RfPlayerException,
            TimeoutError,
        ) as exc:
            reconnect_interval = self.config[CONF_RECONNECT_INTERVAL]
            _LOGGER.exception("Error connecting to RfPlayer, reconnecting in %s", reconnect_interval)
            # Connection to RfPlayer gateway is lost, make entities unavailable
            async_dispatcher_send(self.hass, SIGNAL_RFPLAYER_AVAILABILITY, False)  # type: ignore[has-type]

            reconnect_job = HassJob(self._reconnect_gateway, "RfPlayer reconnect", cancel_on_shutdown=True)
            async_call_later(self.hass, reconnect_interval, reconnect_job)

            raise ConfigEntryNotReady(f"Failed to connect gateway: {exc!s}") from exc

        # There is a valid connection to a RfPlayer gateway now so
        # mark entities as available
        async_dispatcher_send(self.hass, SIGNAL_RFPLAYER_AVAILABILITY, True)  # type: ignore[has-type]

        _LOGGER.info("Connected to RfPlayer")

    @callback
    def _reconnect_gateway(self, _: Exception | None = None) -> None:
        """Schedule reconnect after connection has been unexpectedly lost."""

        async_dispatcher_send(self.hass, SIGNAL_RFPLAYER_AVAILABILITY, False)  # type: ignore[has-type]

        # If HA is not stopping, initiate new connection
        if self.hass.state is not CoreState.stopping:
            _LOGGER.warning("Disconnected from RfPlayer, reconnecting")
            self.hass.async_create_task(self._connect_gateway(), eager_start=False)

    def _send_raw_command(self, call: ServiceCall) -> None:
        client = self._get_client()
        if not client.connected:
            raise PlatformNotReady("RfPlayer not connected")

        command = call.data[ATTR_COMMAND]
        client.send_raw_command(command)

    def _send_pairing_command(self, call: ServiceCall) -> None:
        client = self._get_client()
        if not client.connected:
            raise PlatformNotReady("RfPlayer not connected")

        protocol = call.data[CONF_PROTOCOL]
        address = call.data[CONF_ADDRESS]
        client.send_raw_command(f"ASSOC {protocol} ID {address}")

    async def _simulate_event(self, call: ServiceCall) -> None:
        client = self._get_client()
        if not client.connected:
            raise PlatformNotReady("RfPlayer not connected")

        await client.simulate_event(call.data[ATTR_EVENT_DATA])

    def _get_client(self) -> RfPlayerClient:
        return cast(RfPlayerClient, self.hass.data[DOMAIN][RFPLAYER_CLIENT])
