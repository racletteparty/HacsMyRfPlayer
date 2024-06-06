"""Support for RfPlayer devices."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import copy
import json
import logging
from typing import cast

import slugify
import voluptuous as vol

from custom_components.myrfplayer.rfplayerlib import RfPlayerClient, RfPlayerException
from custom_components.myrfplayer.rfplayerlib.device import RfDeviceEvent, RfDeviceId
from custom_components.myrfplayer.rfplayerlib.protocol import RfPlayerRawEvent
from custom_components.myrfplayer.rfprofiles.registry import (
    AnyRfpPlatformConfig,
    get_profile_registry,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_DEVICE_ID,
    CONF_ADDRESS,
    CONF_DEVICE,
    CONF_DEVICE_ID,
    CONF_DEVICES,
    CONF_EVENT_DATA,
    CONF_MODEL,
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
    ATTR_EVENT_DATA,
    CONF_AUTOMATIC_ADD,
    CONF_GROUP_ID,
    CONF_RECEIVER_PROTOCOLS,
    CONF_RECONNECT_INTERVAL,
    CONNECTION_TIMEOUT,
    DOMAIN,
    RFPLAYER_CLIENT,
    SERVICE_SEND,
    SIGNAL_RFPLAYER_AVAILABILITY,
    SIGNAL_RFPLAYER_EVENT,
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
    device_ids: set[str] = set()

    device_registry = dr.async_get(hass)

    # Declare the RfPlayer event handler
    @callback
    def async_handle_receive(event: RfDeviceEvent) -> None:
        """Handle received messages from RfPlayer gateway."""

        _LOGGER.debug("Receive event: %s", json.dumps(event.data))

        if event.device_id not in device_ids:
            if config[CONF_AUTOMATIC_ADD]:
                _add_rf_device(event)
            else:
                return

        # Callback to HA registered components.
        async_dispatcher_send(hass, SIGNAL_RFPLAYER_EVENT, event)  # type: ignore[has-type]

    @callback
    def _add_rf_device(event: RfDeviceEvent) -> None:
        """Add a device to config entry."""

        _LOGGER.info(
            "Added device %s (Proto: %s Addr: %s Model: %s)",
            event.device.device_id,
            event.device.protocol,
            event.device.address,
            event.device.model,
        )

        data = entry.data.copy()
        data[CONF_DEVICES] = copy.deepcopy(entry.data[CONF_DEVICES])
        data[CONF_DEVICES][event.device.device_id] = _build_device_info_from_event(
            event
        )
        hass.config_entries.async_update_entry(entry=entry, data=data)
        device_ids.add(event.device.device_id)

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
        device_ids.remove(device_id)

    @callback
    def _updated_rf_device(event: Event[EventDeviceRegistryUpdatedData]) -> None:
        if event.data["action"] != "remove":
            return
        device_entry = device_registry.deleted_devices[event.data[ATTR_DEVICE_ID]]
        if entry.entry_id not in device_entry.config_entries:
            return
        device_id = _get_device_id_from_identifiers(device_entry.identifiers)
        if device_id:
            _remove_rf_device(device_id)

    @callback
    def reconnect_gateway(_: Exception | None = None) -> None:
        """Schedule reconnect after connection has been unexpectedly lost."""

        async_dispatcher_send(hass, SIGNAL_RFPLAYER_AVAILABILITY, False)  # type: ignore[has-type]

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
            async_dispatcher_send(hass, SIGNAL_RFPLAYER_AVAILABILITY, False)

            async_call_later(hass, reconnect_interval, _reconnect_job)

            raise ConfigEntryNotReady(f"Failed to connect gateway: {exc!s}") from exc

        # There is a valid connection to a RfPlayer gateway now so
        # mark entities as available
        async_dispatcher_send(hass, SIGNAL_RFPLAYER_AVAILABILITY, True)

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

        event = call.data[ATTR_EVENT_DATA]
        client.send_raw_command(event)

    hass.services.async_register(DOMAIN, SERVICE_SEND, send, schema=SERVICE_SEND_SCHEMA)


async def async_setup_platform_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    platform: Platform,
    builder: Callable[
        [
            RfDeviceId,
            list[AnyRfpPlatformConfig],
            RfPlayerRawEvent | None,
        ],
        list[Entity],
    ],
) -> None:
    """Set up config entry."""
    entry_data = config_entry.data
    # Set of device IDs already configured for the current platform
    device_ids: set[str] = set()

    profile_registy = get_profile_registry()

    # Add entities from config
    entities = []
    for device_id, device_info in entry_data[CONF_DEVICES].items():
        event = _build_event_from_device_info(device_info)

        platform_config = profile_registy.get_platform_config(event.data, platform)
        if not platform_config:
            continue

        assert device_id == event.device_id
        if device_id in device_ids:
            _LOGGER.info(
                "Device %s already configured for platform %s",
                device_id,
                platform,
            )
            continue

        device_ids.add(device_id)
        entities.extend(builder(event.device, platform_config, event.data))

    async_add_entities(entities)

    # If automatic add is on, hookup listener
    if entry_data[CONF_AUTOMATIC_ADD]:

        @callback
        def _update(event: RfDeviceEvent) -> None:
            if event.device_id in device_ids:
                return
            platform_config = profile_registy.get_platform_config(event.data, platform)
            if not platform_config:
                return

            device_ids.add(event.device_id)
            async_add_entities(builder(event.device, platform_config, event.data))

        config_entry.async_on_unload(
            async_dispatcher_connect(hass, SIGNAL_RFPLAYER_EVENT, _update)  # type: ignore[has-type]
        )


async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: ConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    """Remove config entry from a device.

    The actual cleanup is done in the device registry event
    """
    return True


def _get_device_id_from_identifiers(
    identifiers: set[tuple[str, str]],
) -> str:
    """Calculate the device id from a device identifier."""
    return next((x[1] for x in identifiers if x[0] == DOMAIN), "_undefined_")


def _get_identifiers_from_device(
    device: RfDeviceId,
) -> set[tuple[str, str]]:
    """Calculate the device identifier from a device id."""
    return {(DOMAIN, device.device_id)}


def _build_event_from_device_info(device_info: dict) -> RfDeviceEvent:
    protocol = device_info[CONF_PROTOCOL]
    address = device_info[CONF_ADDRESS]
    model = device_info.get(CONF_MODEL)
    group_id = device_info.get(CONF_GROUP_ID)
    event_json_data = device_info.get(CONF_EVENT_DATA)
    event_data = json.loads(event_json_data) if event_json_data else None
    device = RfDeviceId(
        protocol=protocol, address=address, group_id=group_id, model=model
    )
    return RfDeviceEvent(device, data=event_data)


def _build_device_info_from_event(event: RfDeviceEvent) -> dict[str, str]:
    device_info: dict[str, str] = {}
    device_info[CONF_PROTOCOL] = event.device.protocol
    device_info[CONF_ADDRESS] = event.device.address
    device_info[CONF_EVENT_DATA] = json.dumps(event.data)
    return device_info


class RfDeviceEntity(RestoreEntity):
    """Represents a RfPlayer device.

    Contains the common logic for RfPlayer lights and switches.
    """

    _attr_assumed_state = True
    _attr_has_entity_name = True
    _attr_should_poll = False
    _device_id: str
    _event_data: RfPlayerRawEvent | None

    def __init__(
        self,
        device: RfDeviceId,
        event_data: RfPlayerRawEvent | None = None,
    ) -> None:
        """Initialize the device."""
        self._attr_device_info = DeviceInfo(
            identifiers=_get_identifiers_from_device(device),
            model=device.model,
            name=f"{device.protocol} {device.model} {device.address}",
        )
        self._attr_unique_id = slugify.slugify(device.device_id)
        self._event_data = event_data
        self._device_id = device.device_id

    async def async_added_to_hass(self) -> None:
        """Restore RfPlayer device from last event stored in attributes."""
        if (
            self._event_data is None
            and (old_state := await self.async_get_last_state()) is not None
        ):
            json_event_data = cast(str, old_state.attributes.get(ATTR_EVENT_DATA))
            self._event_data = json.loads(json_event_data)

        if self._event_data:
            self._apply_event(self._event_data)

        self.async_on_remove(
            async_dispatcher_connect(  # type: ignore[has-type]
                self.hass, SIGNAL_RFPLAYER_EVENT, self._handle_event
            )
        )

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        """Return the device state attributes."""
        if not self._event_data:
            return None
        return {ATTR_EVENT_DATA: json.dumps(self._event_data)}

    def _event_applies(self, event: RfDeviceEvent) -> bool:
        """Check if event applies to me."""
        return event.device.device_id == self._device_id

    def _apply_event(self, event_data: RfPlayerRawEvent) -> None:
        """Apply a received event."""
        self._event_data = event_data

    @callback
    def _handle_event(self, event: RfDeviceEvent) -> None:
        """Check if event applies to me and update."""
        if not self._event_applies(event):
            return

        self._apply_event(event.data)

        self.async_write_ha_state()


class RfDeviceCommandEntity(RfDeviceEntity):
    """Represents a RfPlayer device.

    Contains the common logic for RfPlayer lights and switches.
    """

    _attr_name = None

    def __init__(
        self,
        device: RfDeviceId,
        event_data: RfPlayerRawEvent | None = None,
    ) -> None:
        """Initialize a switch or light device."""
        super().__init__(device, event_data=event_data)

    async def _async_send[*_Ts](  # type: ignore[valid-type]
        self,
        fun: Callable[[RfPlayerClient, *_Ts], None],  # type: ignore[name-defined]
        *args: *_Ts,  # type: ignore[name-defined]
    ) -> None:
        client: RfPlayerClient = self.hass.data[DOMAIN][RFPLAYER_CLIENT]
        await fun(client, args)  # type: ignore[func-returns-value]
