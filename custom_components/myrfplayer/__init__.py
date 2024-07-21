"""Support for RfPlayer devices."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
import copy
import json
import logging
from typing import Any, cast

import slugify
import voluptuous as vol

from custom_components.myrfplayer.rfplayerlib import RfPlayerClient, RfPlayerException
from custom_components.myrfplayer.rfplayerlib.device import RfDeviceEvent, RfDeviceId
from custom_components.myrfplayer.rfplayerlib.protocol import RfPlayerRawEvent
from custom_components.myrfplayer.rfprofiles import registry
from custom_components.myrfplayer.rfprofiles.registry import (
    DeviceProfile,
    PlatformConfig,
    ProfileRegistry,
    get_profile_registry,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_DEVICE_ID,
    ATTR_ENTITY_ID,
    CONF_ADDRESS,
    CONF_DEVICE,
    CONF_DEVICE_ID,
    CONF_DEVICES,
    CONF_EVENT_DATA,
    CONF_MODEL,
    CONF_PROFILE_NAME,
    CONF_PROTOCOL,
    EVENT_HOMEASSISTANT_STOP,
    Platform,
)
from homeassistant.core import (
    CoreState,
    Event,
    HassJob,
    HomeAssistant,
    ServiceCall,
    callback,
)
from homeassistant.exceptions import ConfigEntryNotReady, PlatformNotReady
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
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    ATTR_COMMAND,
    ATTR_EVENT,
    ATTR_INFO_TYPE,
    ATTR_INFOS,
    CONF_AUTOMATIC_ADD,
    CONF_RECEIVER_PROTOCOLS,
    CONF_RECONNECT_INTERVAL,
    CONNECTION_TIMEOUT,
    DOMAIN,
    EVENT_RFPLAYER_EVENT,
    RFPLAYER_CLIENT,
    SERVICE_SEND,
    SIGNAL_AVAILABILITY,
    SIGNAL_EVENT,
)

_LOGGER = logging.getLogger(__name__)

SERVICE_SEND_SCHEMA = vol.Schema({ATTR_COMMAND: str})

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the RfPlayer component."""
    hass.data.setdefault(
        DOMAIN,
        {CONF_DEVICE: entry.data[CONF_DEVICE], CONF_DEVICES: {}},
    )

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


async def async_setup_internal(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Set up the RfPlayer component."""
    config = entry.data

    # Setup some per rf device config
    devices = hass.data[DOMAIN][CONF_DEVICES]

    # TODO create gateway device ?
    # TODO create rf devices from RfDeviceEntity but needs at least 1 entity

    device_registry = dr.async_get(hass)

    # Declare the Handle event
    @callback
    def async_handle_receive(event: RfDeviceEvent) -> None:
        """Handle received messages from RfPlayer gateway."""

        _LOGGER.debug("Receive event: %s", event)

        event_data = {
            ATTR_DEVICE_ID: event.device_id,
            ATTR_INFO_TYPE: event.info_type,
            ATTR_INFOS: event.infos,
        }

        if event.device_id not in devices:
            if config[CONF_AUTOMATIC_ADD]:
                _add_rf_device(event)
            else:
                return

        device_entry = device_registry.async_get_device(
            identifiers={(DOMAIN, event.device.device_id)},
        )
        if device_entry:
            event_data[ATTR_ENTITY_ID] = device_entry.id

        # Callback to HA registered components.
        async_dispatcher_send(hass, SIGNAL_EVENT, event, event.device_id)

        # Signal event to any other listeners
        hass.bus.async_fire(EVENT_RFPLAYER_EVENT, event_data)

    @callback
    def _add_rf_device(event: RfDeviceEvent) -> None:
        """Add a device to config entry."""

        config = {}
        config[CONF_DEVICE_ID] = event.device.device_id
        config[CONF_PROTOCOL] = event.device.protocol
        config[CONF_ADDRESS] = event.device.address
        config[CONF_EVENT_DATA] = json.dumps(event.data)

        _LOGGER.info(
            "Added device %s (Proto: %s Addr: %s Model: %s)",
            event.device.device_id,
            event.device.protocol,
            event.device.address,
            event.device.model,
        )

        data = entry.data.copy()
        data[CONF_DEVICES] = copy.deepcopy(entry.data[CONF_DEVICES])
        data[CONF_DEVICES][event.device.device_id] = config
        hass.config_entries.async_update_entry(entry=entry, data=data)
        devices[event.device.device_id] = config
        # TODO call device_registry.async_get_or_create ?

    @callback
    def _remove_rf_device(device_id: str) -> None:
        data = {
            **entry.data,
            CONF_DEVICES: {
                device_config_id: entity_info
                for device_config_id, entity_info in entry.data[CONF_DEVICES].items()
                if entity_info.get(CONF_DEVICE_ID) != device_id
            },
        }
        hass.config_entries.async_update_entry(entry=entry, data=data)
        devices.pop(device_id)

    @callback
    def _updated_rf_device(event: Event[EventDeviceRegistryUpdatedData]) -> None:
        if event.data["action"] != "remove":
            return
        device_entry = device_registry.deleted_devices[event.data[ATTR_ENTITY_ID]]
        if entry.entry_id not in device_entry.config_entries:
            return
        device_id = get_device_id_from_identifiers(device_entry.identifiers)
        if device_id:
            _remove_rf_device(device_id)

    @callback
    def reconnect_gateway(_: Exception | None = None) -> None:
        """Schedule reconnect after connection has been unexpectedly lost."""

        async_dispatcher_send(hass, SIGNAL_AVAILABILITY, False)

        # If HA is not stopping, initiate new connection
        if hass.state is not CoreState.stopping:
            _LOGGER.warning("Disconnected from RfPlayer, reconnecting")
            hass.async_create_task(connect_gateway(), eager_start=False)

    _reconnect_job = HassJob(
        reconnect_gateway, "RfPlayer reconnect", cancel_on_shutdown=True
    )

    # Initialize library
    client = RfPlayerClient(
        event_callback=async_handle_receive,
        disconnect_callback=reconnect_gateway,
        loop=hass.loop,
        port=config[CONF_DEVICE],
        receiver_protocols=config[CONF_RECEIVER_PROTOCOLS],
    )
    hass.data[DOMAIN][RFPLAYER_CLIENT] = client

    async def connect_gateway():
        """Set up connection and hook it into HA for reconnect/shutdown."""
        _LOGGER.info("Initiating RFPlayer connection")

        try:
            async with asyncio.timeout(CONNECTION_TIMEOUT):
                await client.connect()

        except (
            RfPlayerException,
            TimeoutError,
        ) as exc:
            reconnect_interval = config[CONF_RECONNECT_INTERVAL]
            _LOGGER.exception(
                "Error connecting to RfPlayer, reconnecting in %s", reconnect_interval
            )
            # Connection to RfPlayer gateway is lost, make entities unavailable
            async_dispatcher_send(hass, SIGNAL_AVAILABILITY, False)

            async_call_later(hass, reconnect_interval, _reconnect_job)

            raise ConfigEntryNotReady(f"Failed to connect gateway: {exc!s}") from exc

        # There is a valid connection to a RfPlayer gateway now so
        # mark entities as available
        async_dispatcher_send(hass, SIGNAL_AVAILABILITY, True)

        _LOGGER.info("Connected to RfPlayer")

    await entry.async_create_task(hass, connect_gateway())

    entry.async_on_unload(
        hass.bus.async_listen(dr.EVENT_DEVICE_REGISTRY_UPDATED, _updated_rf_device)
    )

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, lambda _: client.close())
    )

    def send(call: ServiceCall) -> None:
        if not client.connected:
            raise PlatformNotReady("RfPlayer not connected")

        event = call.data[ATTR_EVENT]
        client.send_raw_command(event)

    hass.services.async_register(DOMAIN, SERVICE_SEND, send, schema=SERVICE_SEND_SCHEMA)


async def async_setup_platform_entry(
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    platform_name: str,
    builder: Callable[
        [
            RfDeviceId,
            dict[str, PlatformConfig],
            RfDeviceEvent | None,
        ],
        list[Entity],
    ],
) -> None:
    """Set up config entry."""
    entry_data = config_entry.data
    device_ids: set[str] = set()

    profile_registy = get_profile_registry()

    # Add entities from config
    entities = []
    for device_id, device_info in entry_data[CONF_DEVICES].items():
        protocol = device_info[CONF_PROTOCOL]
        address = device_info[CONF_ADDRESS]
        model = device_info.get(CONF_MODEL)
        event_json_data = device_info.get(CONF_EVENT_DATA)
        event_data = json.loads(event_json_data) if event_json_data else None
        profile_name = device_info.get(CONF_PROFILE_NAME)
        device = RfDeviceId(protocol=protocol, address=address, model=model)
        event = RfDeviceEvent(device, event_data) if event_data else None

        profile = profile_registy.get_profile(profile_name)

        platform_config = profile.platforms.get(platform_name)
        if not platform_config:
            _LOGGER.debug(
                "Platform %s not supported by profile %s", platform_name, profile_name
            )
            continue

        # De-duplicate
        assert device_id == device.device_id
        device_ids.add(device.device_id)
        if device.device_id in device_ids:
            _LOGGER.info("Device id duplicated %s", device.device_id)
            continue

        entities.extend(builder(device, platform_config, event, device_info))

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


def get_identifiers_from_device(
    device: RfDeviceId,
) -> set[tuple[str, str]]:
    """Calculate the device identifier from a device id."""
    return {(DOMAIN, device.device_id)}


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
        event_data: RfPlayerRawEvent | None = None,
    ) -> None:
        """Initialize the device."""
        self._attr_device_info = DeviceInfo(
            identifiers=get_identifiers_from_device(device),
            model=device.model,
            name=f"{device.protocol} {device.model} {device.address}",
        )
        self._attr_unique_id = slugify(device.device_id)
        self._device = device
        self._event = (
            RfDeviceEvent(device=device, data=event_data) if event_data else None
        )
        self._device_id = device.device_id

    async def async_added_to_hass(self) -> None:
        """Restore RfPlayer device from last event stored in attributes."""
        if (
            self._event is None
            and (old_state := await self.async_get_last_state()) is not None
            and (json_event := old_state.attributes.get(ATTR_EVENT))
        ):
            self._event = json.load(json_event)

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
        return {ATTR_EVENT: json.dumps(self._event)}

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
        super().__init__(device, event_data=event)

    async def _async_send[*_Ts](
        self, fun: Callable[[RfPlayerClient, *_Ts], None], *args: *_Ts
    ) -> None:
        client: RfPlayerClient = self.hass.data[DOMAIN][RFPLAYER_CLIENT]
        await fun(client, args)
