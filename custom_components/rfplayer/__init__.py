"""Support for RfPlayer devices."""

from __future__ import annotations

import binascii
from collections.abc import Callable, Mapping
import copy
import logging
from typing import Any, NamedTuple, cast

import voluptuous as vol

from custom_components.rfplayer.rfplayerlib import RfPlayerDevice, RfPlayerEvent
from custom_components.rfplayer.rfplayerlib.client import (
    JsonPacketType,
    RfPlayerClient,
    RfPlayerEventType,
    RfPlayerException,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_DEVICE_ID,
    CONF_DEVICE,
    CONF_DEVICE_ID,
    CONF_DEVICES,
    CONF_HOST,
    CONF_PORT,
    EVENT_HOMEASSISTANT_STOP,
    Platform,
)
from homeassistant.core import Event, HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.device_registry import (
    DeviceInfo,
    EventDeviceRegistryUpdatedData,
)
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    ATTR_COMMAND,
    ATTR_EVENT,
    CONF_AUTOMATIC_ADD,
    CONF_PROTOCOLS,
    DOMAIN,
    EVENT_RFPLAYER_EVENT,
    RFPLAYER_CLIENT,
    SERVICE_SEND,
)

DEFAULT_OFF_DELAY = 2.0

SIGNAL_EVENT = f"{DOMAIN}_event"
CONNECT_TIMEOUT = 30.0

_LOGGER = logging.getLogger(__name__)


class DeviceTuple(NamedTuple):
    """Representation of a device in rfplayer."""

    packettype: str
    subtype: str
    id_string: str


SERVICE_SEND_SCHEMA = vol.Schema({ATTR_COMMAND: str})

PLATFORMS = [
    Platform.BINARY_SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the RfPlayer component."""
    hass.data.setdefault(DOMAIN, {})

    await async_setup_internal(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload RfPlayer component."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False

    hass.services.async_remove(DOMAIN, SERVICE_SEND)

    client = hass.data[DOMAIN][RFPLAYER_CLIENT]
    await hass.async_add_executor_job(client.close_connection)

    hass.data.pop(DOMAIN)

    return True


async def _create_rfp_client(
    config: Mapping[str, Any],
    event_callback: Callable[[RfPlayerEventType], None],
    disconnect_callback: Callable[[Exception | None], None],
) -> RfPlayerClient:
    """Construct a rfplayer client based on config."""

    modes = config.get(CONF_PROTOCOLS)

    if modes:
        _LOGGER.debug("Using modes: %s", ",".join(modes))
    else:
        _LOGGER.debug("No modes defined, using device configuration")

    client = RfPlayerClient(
        event_callback=event_callback,
        disconnect_callback=disconnect_callback,
        loop=None,
        port=config[CONF_DEVICE],
    )

    try:
        await client.connect()
    except RfPlayerException as exc:
        raise ConfigEntryNotReady(str(exc)) from exc

    return client


def _get_device_lookup(
    devices: dict[str, dict[str, Any]],
) -> dict[DeviceTuple, dict[str, Any]]:
    """Get a lookup structure for devices."""
    lookup = {}
    for event_code, event_config in devices.items():
        if (event := get_rfx_object(event_code)) is None:
            continue
        device_id = get_device_id(
            event.device, data_bits=event_config.get(CONF_DATA_BITS)
        )
        lookup[device_id] = event_config
    return lookup


async def async_setup_internal(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Set up the RfPlayer component."""
    config = entry.data

    # Setup some per device config
    devices = _get_device_lookup(config[CONF_DEVICES])

    device_registry = dr.async_get(hass)

    # Declare the Handle event
    @callback
    def async_handle_receive(event: RfPlayerEvent) -> None:
        """Handle received messages from RfPlayer gateway."""

        _LOGGER.debug("Receive event: %s", event)

        data_bits = get_device_data_bits(event.device, devices)
        device_id = get_device_id(event.device, data_bits=data_bits)

        event_data = {
            ATTR_DEVICE_ID:
        }

        if device_id not in devices:
            if config[CONF_AUTOMATIC_ADD]:
                _add_device(event, device_id)
            else:
                return

        device_entry = device_registry.async_get_device(
            identifiers={(DOMAIN, event.device.unique_id)},
        )
        if device_entry:
            event_data[ATTR_DEVICE_ID] = device_entry.id

        # Callback to HA registered components.
        async_dispatcher_send(hass, SIGNAL_EVENT, event, device_id)

        # Signal event to any other listeners
        hass.bus.async_fire(EVENT_RFPLAYER_EVENT, event_data)

    @callback
    def _add_device(event: RfPlayerEventType, device_id: DeviceTuple) -> None:
        """Add a device to config entry."""
        config = {}
        config[CONF_DEVICE_ID] = device_id

        _LOGGER.info(
            "Added device (Device ID: %s Class: %s Sub: %s, Event: %s)",
            event.device.id_string.lower(),
            event.device.__class__.__name__,
            event.device.subtype,
            "".join(f"{x:02x}" for x in event.data),
        )

        data = entry.data.copy()
        data[CONF_DEVICES] = copy.deepcopy(entry.data[CONF_DEVICES])
        event_code = binascii.hexlify(event.data).decode("ASCII")
        data[CONF_DEVICES][event_code] = config
        hass.config_entries.async_update_entry(entry=entry, data=data)
        devices[device_id] = config

    @callback
    def _remove_device(device_id: DeviceTuple) -> None:
        data = {
            **entry.data,
            CONF_DEVICES: {
                packet_id: entity_info
                for packet_id, entity_info in entry.data[CONF_DEVICES].items()
                if tuple(entity_info.get(CONF_DEVICE_ID)) != device_id
            },
        }
        hass.config_entries.async_update_entry(entry=entry, data=data)
        devices.pop(device_id)

    @callback
    def _updated_device(event: Event[EventDeviceRegistryUpdatedData]) -> None:
        if event.data["action"] != "remove":
            return
        device_entry = device_registry.deleted_devices[event.data["device_id"]]
        if entry.entry_id not in device_entry.config_entries:
            return
        device_id = get_device_tuple_from_identifiers(device_entry.identifiers)
        if device_id:
            _remove_device(device_id)

    # Initialize library
    client = await hass.async_add_executor_job(
        _create_rfp_client,
        config,
        lambda event: hass.add_job(async_handle_receive, event),
    )

    hass.data[DOMAIN][RFPLAYER_CLIENT] = client

    entry.async_on_unload(
        hass.bus.async_listen(dr.EVENT_DEVICE_REGISTRY_UPDATED, _updated_device)
    )

    def _shutdown_client(event: Event) -> None:
        """Close connection with RfPlayer."""
        client.close_connection()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _shutdown_client)
    )

    def send(call: ServiceCall) -> None:
        event = call.data[ATTR_EVENT]
        client.send(event)

    hass.services.async_register(DOMAIN, SERVICE_SEND, send, schema=SERVICE_SEND_SCHEMA)


async def async_setup_platform_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    supported: Callable[[RfPlayerEvent], bool],
    constructor: Callable[
        [
            RfPlayerEvent,
            RfPlayerEvent | None,
            dict[str, Any],
        ],
        list[Entity],
    ],
) -> None:
    """Set up config entry."""
    entry_data = config_entry.data
    device_ids: set[str] = set()

    # Add entities from config
    entities = []
    for packet_id, entity_info in entry_data[CONF_DEVICES].items():
        if (event := get_rfx_object(packet_id)) is None:
            _LOGGER.error("Invalid device: %s", packet_id)
            continue
        if not supported(event):
            continue

        device_id = get_device_id(
            event.device, data_bits=entity_info.get(CONF_DATA_BITS)
        )
        if device_id in device_ids:
            continue
        device_ids.add(device_id)

        entities.extend(constructor(event, None, device_id, entity_info))

    async_add_entities(entities)

    # If automatic add is on, hookup listener
    if entry_data[CONF_AUTOMATIC_ADD]:

        @callback
        def _update(event: RfPlayerEvent) -> None:
            """Handle light updates from the RfPlayer gateway."""
            if not supported(event):
                return

            if event.device.unique_id in device_ids:
                return
            device_ids.add(device_id)
            async_add_entities(constructor(event, event, device_id, {}))

        config_entry.async_on_unload(
            async_dispatcher_connect(hass, SIGNAL_EVENT, _update)
        )

async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: ConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    """Remove config entry from a device.

    The actual cleanup is done in the device registry event
    """
    return True


class RfPlayerEntity(RestoreEntity):
    """Represents a RfPlayer device.

    Contains the common logic for RfPlayer lights and switches.
    """

    _attr_assumed_state = True
    _attr_has_entity_name = True
    _attr_should_poll = False
    _device: RfPlayerDevice
    _event: RfPlayerEvent | None

    def __init__(
        self,
        device: RfPlayerDevice,
        event:RfPlayerEvent | None = None,
    ) -> None:
        """Initialize the device."""
        self._attr_device_info = DeviceInfo(
            identifiers=get_identifiers_from_device_tuple(device_id),
            model=device.type_string,
            name=f"{device.type_string} {device.id_string}",
        )
        self._attr_unique_id = "_".join(x for x in device_id)
        self._device = device
        self._event = event
        self._device_id = device_id
        # If id_string is 213c7f2:1, the group_id is 213c7f2, and the device will respond to
        # group events regardless of their group indices.
        (self._group_id, _, _) = cast(str, device.id_string).partition(":")

    async def async_added_to_hass(self) -> None:
        """Restore RfPlayer device state (ON/OFF)."""
        if self._event:
            self._apply_event(self._event)

        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_EVENT, self._handle_event)
        )

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        """Return the device state attributes."""
        if not self._event:
            return None
        return {ATTR_EVENT: "".join(f"{x:02x}" for x in self._event.data)}

    def _event_applies(self, event: RfPlayerEventType, device_id: DeviceTuple) -> bool:
        """Check if event applies to me."""
        if isinstance(event, RfPlayermod.ControlEvent):
            if (
                "Command" in event.values
                and event.values["Command"] in COMMAND_GROUP_LIST
            ):
                device: RfPlayermod.RfPlayerDevice = event.device
                (group_id, _, _) = cast(str, device.id_string).partition(":")
                return group_id == self._group_id

        # Otherwise, the event only applies to the matching device.
        return device_id == self._device_id

    def _apply_event(self, event: RfPlayerEventType) -> None:
        """Apply a received event."""
        self._event = event

    @callback
    def _handle_event(self, event: RfPlayerEventType, device_id: DeviceTuple) -> None:
        """Handle a reception of data, overridden by other classes."""


class RfPlayerCommandEntity(RfPlayerEntity):
    """Represents a RfPlayer device.

    Contains the common logic for RfPlayer lights and switches.
    """

    _attr_name = None

    def __init__(
        self,
        device: RfPlayermod.RfPlayerDevice,
        device_id: DeviceTuple,
        event: RfPlayerEventType | None = None,
    ) -> None:
        """Initialzie a switch or light device."""
        super().__init__(device, device_id, event=event)

    async def _async_send[*_Ts](
        self, fun: Callable[[RfPlayerClient, *_Ts], None], *args: *_Ts
    ) -> None:
        client: RfPlayerClient = self.hass.data[DOMAIN][RFPLAYER_CLIENT]
        await self.hass.async_add_executor_job(fun, client, *args)
