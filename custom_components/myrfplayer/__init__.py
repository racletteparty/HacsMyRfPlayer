"""Support for RfPlayer devices."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import copy
import logging
from typing import Any, cast

import slugify
import voluptuous as vol

from custom_components.myrfplayer.rfplayerlib import RfPlayerClient, RfPlayerException
from custom_components.myrfplayer.rfplayerlib.device import RfDeviceEvent, RfDeviceId
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_DEVICE_ID,
    ATTR_ENTITY_ID,
    CONF_DEVICE,
    CONF_DEVICE_ID,
    CONF_DEVICES,
    EVENT_HOMEASSISTANT_STOP,
    Platform,
)
from homeassistant.core import Event, HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
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
    DOMAIN,
    EVENT_RFPLAYER_EVENT,
    RFPLAYER_CLIENT,
    SERVICE_SEND,
)

SIGNAL_EVENT = f"{DOMAIN}_event"

_LOGGER = logging.getLogger(__name__)

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

    client = cast(RfPlayerClient, hass.data[DOMAIN][RFPLAYER_CLIENT])
    await hass.async_add_executor_job(client.close)

    hass.data.pop(DOMAIN)

    return True


async def _create_rfp_client(
    config: Mapping[str, Any],
    event_callback: Callable[[RfDeviceEvent], None],
    disconnect_callback: Callable[[Exception | None], None],
) -> RfPlayerClient:
    """Construct a rfplayer client based on config."""

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


async def async_setup_internal(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Set up the RfPlayer component."""
    config = entry.data

    # Setup some per device config
    devices = config[CONF_DEVICES]

    device_registry = dr.async_get(hass)

    # Declare the Handle event
    @callback
    def async_handle_receive(event: RfDeviceEvent) -> None:
        """Handle received messages from RfPlayer gateway."""

        _LOGGER.debug("Receive event: %s", event)

        device_id = event.device.device_id

        event_data = {ATTR_DEVICE_ID: device_id}

        if device_id not in devices:
            if config[CONF_AUTOMATIC_ADD]:
                _add_device(device_id, event)
            else:
                return

        device_entry = device_registry.async_get_device(
            identifiers={(DOMAIN, event.device.device_id)},
        )
        if device_entry:
            event_data[ATTR_ENTITY_ID] = device_entry.id

        # Callback to HA registered components.
        async_dispatcher_send(hass, SIGNAL_EVENT, event, device_id)

        # Signal event to any other listeners
        hass.bus.async_fire(EVENT_RFPLAYER_EVENT, event_data)

    @callback
    def _add_device(device_id: str, event: RfDeviceEvent) -> None:
        """Add a device to config entry."""
        config = {}
        config[CONF_DEVICE_ID] = device_id

        _LOGGER.info(
            "Added device (Device Proto: %s Type: %s Addr: %s)",
            event.device.protocol,
            event.device.device_type,
            event.device.address,
        )

        data = entry.data.copy()
        data[CONF_DEVICES] = copy.deepcopy(entry.data[CONF_DEVICES])
        data[CONF_DEVICES][device_id] = config
        hass.config_entries.async_update_entry(entry=entry, data=data)
        devices[device_id] = config

    @callback
    def _remove_device(device_id: str) -> None:
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
        device_entry = device_registry.deleted_devices[event.data[ATTR_ENTITY_ID]]
        if entry.entry_id not in device_entry.config_entries:
            return
        device_id = get_device_tuple_from_identifiers(device_entry.identifiers)
        if device_id:
            _remove_device(device_id)

    # Initialize library
    client = cast(
        RfPlayerClient,
        await hass.add_job(
            _create_rfp_client,
            config,
            lambda event: hass.add_job(async_handle_receive, event),
        ),
    )

    hass.data[DOMAIN][RFPLAYER_CLIENT] = client

    entry.async_on_unload(
        hass.bus.async_listen(dr.EVENT_DEVICE_REGISTRY_UPDATED, _updated_device)
    )

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, lambda _: client.close())
    )

    def send(call: ServiceCall) -> None:
        event = call.data[ATTR_EVENT]
        client.send_raw_command(event)

    hass.services.async_register(DOMAIN, SERVICE_SEND, send, schema=SERVICE_SEND_SCHEMA)


async def async_setup_platform_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    supported: Callable[[RfDeviceEvent], bool],
    constructor: Callable[
        [
            RfDeviceEvent,
            RfDeviceEvent | None,
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


async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: ConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    """Remove config entry from a device.

    The actual cleanup is done in the device registry event
    """
    return True


def get_device_id_from_identifiers(
    identifiers: set[tuple[str, str]],
) -> str:
    """Calculate the device id from a device identifier."""
    return next((x[1] for x in identifiers if x[0] == DOMAIN), None)


def get_identifiers_from_device_id(
    device_id: str,
) -> set[tuple[str, str]]:
    """Calculate the device identifier from a device id."""
    return {(DOMAIN, device_id)}


class RfDeviceEntity(RestoreEntity):
    """Represents a RfPlayer device.

    Contains the common logic for RfPlayer lights and switches.
    """

    _attr_assumed_state = True
    _attr_has_entity_name = True
    _attr_should_poll = False
    _device: RfDeviceId
    _event: RfDeviceEvent | None

    def __init__(
        self,
        device: RfDeviceId,
        event: RfDeviceEvent | None = None,
    ) -> None:
        """Initialize the device."""
        self._attr_device_info = DeviceInfo(
            identifiers=get_identifiers_from_device_id(device.device_id),
            model=device.device_type,
            name=f"{device.protocol} {device.device_type} {device.address}",
        )
        self._attr_unique_id = slugify(device.device_id)
        self._device = device
        self._event = event
        self._device_id = device.device_id

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

    def _event_applies(self, event: RfDeviceEvent) -> bool:
        """Check if event applies to me."""
        # Otherwise, the event only applies to the matching device.
        return event.device.device_id == self._device_id

    def _apply_event(self, event: RfDeviceEvent) -> None:
        """Apply a received event."""
        self._event = event

    @callback
    def _handle_event(self, event: RfDeviceEvent) -> None:
        """Handle a reception of data, overridden by other classes."""


class RfDeviceCommandEntity(RfDeviceEntity):
    """Represents a RfPlayer device.

    Contains the common logic for RfPlayer lights and switches.
    """

    _attr_name = None

    def __init__(
        self,
        device: RfDeviceId,
        event: RfDeviceEvent | None = None,
    ) -> None:
        """Initialzie a switch or light device."""
        super().__init__(device, event=event)

    async def _async_send[*_Ts](
        self, fun: Callable[[RfPlayerClient, *_Ts], None], *args: *_Ts
    ) -> None:
        client: RfPlayerClient = self.hass.data[DOMAIN][RFPLAYER_CLIENT]
        await fun(client, args)
