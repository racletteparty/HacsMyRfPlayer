"""The tests for the RfPlayer component."""

from __future__ import annotations

from typing import cast
from unittest.mock import ANY, Mock

from pytest_homeassistant_custom_component.typing import WebSocketGenerator
from pytest_mock import MockerFixture
from serial import SerialException

from custom_components.myrfplayer.const import (
    DOMAIN,
    RFPLAYER_CLIENT,
    SIGNAL_RFPLAYER_EVENT,
)
from custom_components.myrfplayer.rfplayerlib import RfPlayerClient
from custom_components.myrfplayer.rfplayerlib.device import RfDeviceEvent, RfDeviceId
from custom_components.myrfplayer.rfplayerlib.protocol import (
    JsonPacketType,
    RfplayerProtocol,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component

from .conftest import setup_rfplayer_test_cfg

SOME_PROTOCOLS = ["X2D", "RTS"]


async def test_fire_event(
    serial_connection_mock: Mock,
    hass: HomeAssistant,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test fire event."""
    await setup_rfplayer_test_cfg(
        hass, device="/dev/serial/by-id/usb-rfplayer-port0", automatic_add=True
    )

    calls = []

    @callback
    def record_event(event: RfDeviceEvent):
        """Add recorded event to set."""
        calls.append(event)

    hass.bus.async_listen(SIGNAL_RFPLAYER_EVENT, record_event)

    client = cast(RfPlayerClient, hass.data[DOMAIN][RFPLAYER_CLIENT])

    client.event_callback(
        RfDeviceEvent(
            device=RfDeviceId(
                protocol="OREGON", address="39168", model="PCR800", group_id=None
            ),
            data=JsonPacketType(
                {
                    "frame": {
                        "header": {
                            "frameType": "0",
                            "dataFlag": "0",
                            "rfLevel": "-71",
                            "floorNoise": "-98",
                            "rfQuality": "5",
                            "protocol": "5",
                            "protocolMeaning": "OREGON",
                            "infoType": "9",
                            "frequency": "433920",
                        },
                        "infos": {
                            "subType": "0",
                            "id_PHY": "0x2A19",
                            "id_PHYMeaning": "PCR800",
                            "adr_channel": "39168",
                            "adr": "153",
                            "channel": "0",
                            "qualifier": "48",
                            "lowBatt": "0",
                            "measures": [
                                {"type": "total rain", "value": "1040.1", "unit": "mm"},
                                {
                                    "type": "current rain",
                                    "value": "0.00",
                                    "unit": "mm/h",
                                },
                            ],
                        },
                    }
                }
            ),
        )
    )

    client.event_callback(
        RfDeviceEvent(
            device=RfDeviceId(
                protocol="BLYSS", address="4261483730", model=None, group_id=None
            ),
            data=JsonPacketType(
                {
                    "frame": {
                        "header": {
                            "frameType": "0",
                            "dataFlag": "0",
                            "rfLevel": "-41",
                            "floorNoise": "-97",
                            "rfQuality": "10",
                            "protocol": "3",
                            "protocolMeaning": "BLYSS",
                            "infoType": "1",
                            "frequency": "433920",
                        },
                        "infos": {
                            "subType": "0",
                            "id": "4261483730",
                            "subTypeMeaning": "OFF",
                        },
                    }
                }
            ),
        )
    )

    client.event_callback(
        RfDeviceEvent(
            device=RfDeviceId(
                protocol="GATEWAY", address="a_player", model="gateway", group_id=None
            ),
            data="Welcome to Ziblue Dongle RFPLAYER (RFP1000, Firmware V1.12Mac 0xF6C09FA1)!",
        )
    )

    device_id_1 = device_registry.async_get_device(
        identifiers={("myrfplayer", "OREGON-39168")}
    )
    assert device_id_1

    device_id_2 = device_registry.async_get_device(
        identifiers={("myrfplayer", "BLYSS-4261483730")}
    )
    assert device_id_2

    device_id_3 = device_registry.async_get_device(
        identifiers={("myrfplayer", "GATEWAY.a_player")}
    )
    assert device_id_3

    assert calls == [
        {
            "device_id": device_id_1.id,
            "info_type": 9,
            "infos": {
                "subType": "0",
                "id_PHY": "0x2A19",
                "id_PHYMeaning": "PCR800",
                "adr_channel": "39168",
                "adr": "153",
                "channel": "0",
                "qualifier": "48",
                "lowBatt": "0",
                "measures": [
                    {"type": "total rain", "value": "1040.1", "unit": "mm"},
                    {"type": "current rain", "value": "0.00", "unit": "mm/h"},
                ],
            },
        },
        {
            "device_id": device_id_2.id,
            "info_type": 1,
            "infos": {"subType": "0", "id": "4261483730", "subTypeMeaning": "OFF"},
        },
        {
            "device_id": device_id_3.id,
            "info_type": -1,
            "infos": {
                "response": "Welcome to Ziblue Dongle RFPLAYER (RFP1000, Firmware V1.12Mac 0xF6C09FA1)!"
            },
        },
    ]


async def test_send(
    serial_connection_mock: Mock, test_protocol: RfplayerProtocol, hass: HomeAssistant
) -> None:
    """Test configuration."""
    await setup_rfplayer_test_cfg(hass, device="/dev/null", devices={})

    await hass.services.async_call(
        "myrfplayer", "send", {"event": "0a520802060101ff0f0269"}, blocking=True
    )

    test_protocol.transport.write.assert_called_once_with(
        bytearray(b"\x0a\x52\x08\x02\x06\x01\x01\xff\x0f\x02\x69")
    )


async def test_ws_device_remove(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    device_registry: dr.DeviceRegistry,
) -> None:
    """Test removing a device through device registry."""
    assert await async_setup_component(hass, "config", {})

    device_id = ["11", "0", "213c7f2:16"]
    mock_entry = await setup_rfplayer_test_cfg(
        hass,
        devices={
            "0b1100cd0213c7f210010f51": {"fire_event": True, "device_id": device_id},
        },
    )

    device_entry = device_registry.async_get_device(
        identifiers={("myrfplayer", *device_id)}
    )
    assert device_entry

    # Ask to remove existing device
    client = await hass_ws_client(hass)
    response = await client.remove_device(device_entry.id, mock_entry.entry_id)
    assert response["success"]

    # Verify device entry is removed
    assert (
        device_registry.async_get_device(identifiers={("myrfplayer", *device_id)})
        is None
    )

    # Verify that the config entry has removed the device
    assert mock_entry.data["devices"] == {}


async def test_connect(serial_connection_mock: Mock, hass: HomeAssistant) -> None:
    """Test that we attempt to connect to the device."""

    config_entry = await setup_rfplayer_test_cfg(hass, device="/dev/ttyUSBfake")
    serial_connection_mock.assert_called_once_with(
        hass.loop, ANY, "/dev/ttyUSBfake", 115200
    )
    assert config_entry.state is ConfigEntryState.LOADED


async def test_connect_with_protocols(
    serial_connection_mock: Mock, hass: HomeAssistant
) -> None:
    """Test that we attempt to set protocols."""

    config_entry = await setup_rfplayer_test_cfg(
        hass, device="/dev/ttyUSBfake", protocols=SOME_PROTOCOLS
    )
    client = cast(RfPlayerClient, hass.data[DOMAIN][RFPLAYER_CLIENT])

    serial_connection_mock.assert_called_once_with(
        hass.loop, ANY, "/dev/ttyUSBfake", 115200
    )

    assert client.receiver_protocols == SOME_PROTOCOLS
    assert config_entry.state is ConfigEntryState.LOADED


async def test_connect_timeout(
    serial_connection_mock: Mock, mocker: MockerFixture, hass: HomeAssistant
) -> None:
    """Test that we attempt to connect to the device."""

    mocker.patch(
        "custom_components.myrfplayer.asyncio.timeout"
    ).side_effect = TimeoutError

    config_entry = await setup_rfplayer_test_cfg(hass, device="/dev/ttyUSBfake")

    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_connect_failed(
    serial_connection_mock: Mock, hass: HomeAssistant
) -> None:
    """Test that we attempt to connect to the device."""

    serial_connection_mock.side_effect = SerialException

    config_entry = await setup_rfplayer_test_cfg(hass, device="/dev/ttyUSBfake")
    serial_connection_mock.assert_called_once_with(
        hass.loop, ANY, "/dev/ttyUSBfake", 115200
    )

    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_reconnect(serial_connection_mock, hass: HomeAssistant) -> None:
    """Test that we reconnect on connection loss."""

    # GIVEN
    config_entry = await setup_rfplayer_test_cfg(hass, device="/dev/ttyUSBfake")
    client = cast(RfPlayerClient, hass.data[DOMAIN][RFPLAYER_CLIENT])

    assert client is not None
    assert config_entry.state is ConfigEntryState.LOADED
    serial_connection_mock.call_count = 1

    # WHEN
    client.disconnect_callback()
    await hass.async_block_till_done()

    # THEN
    assert config_entry.state is ConfigEntryState.LOADED
    serial_connection_mock.call_count = 2
