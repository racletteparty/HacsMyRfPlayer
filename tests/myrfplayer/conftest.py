"""Common test tools."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import cast
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_mock import MockerFixture

from custom_components.myrfplayer.rfplayerlib import RfPlayerClient, RfplayerProtocol
from custom_components.myrfplayer.rfplayerlib.device import RfDeviceEvent


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):  # pylint: disable=unused-argument
    """Automatically enable loading custom integrations in all tests."""
    return


@pytest.fixture
def test_protocol() -> RfplayerProtocol:
    """Create a rfclient protocol with patched event loop."""

    transport = Mock(spec=asyncio.WriteTransport)
    event_callback = Mock(spec=callable)
    disconnect_callback = Mock(spec=callable)
    loop = Mock()
    protocol = RfplayerProtocol(
        id=str(uuid4()),
        event_callback=event_callback,
        disconnect_callback=disconnect_callback,
        loop=loop,
        init_script=["LEDACTIVITY 0", "JAMMING 10"],
    )
    protocol.transport = transport
    return protocol


@pytest.fixture
def serial_connection_mock(
    mocker: MockerFixture, test_protocol: RfplayerProtocol
) -> Mock:
    """Patch create_serial_connection to return mock protocol."""

    return mocker.patch(
        "custom_components.myrfplayer.rfplayerlib.create_serial_connection",
        return_value=(None, test_protocol),
    )


@pytest.fixture
def test_client(
    serial_connection_mock: Mock, test_protocol: RfplayerProtocol
) -> RfPlayerClient:
    """Create a rfclient with patch serial connection."""

    return RfPlayerClient(
        event_callback=cast(
            Callable[[RfDeviceEvent], None], test_protocol.event_callback
        ),
        disconnect_callback=test_protocol.disconnect_callback,
        loop=Mock(spec=asyncio.AbstractEventLoop),
        port="/dev/ttyUSB0",
        baud=115200,
        receiver_protocols=["X2D", "RTS"],
    )


def create_rfplayer_test_cfg(
    device="abcd",
    automatic_add=False,
    protocols=None,
    devices=None,
):
    """Create rfplayer config entry data."""
    return {
        "device": device,
        "automatic_add": automatic_add,
        "receiver_protocols": protocols,
        "devices": devices or {},
        "reconnect_interval": 10,
    }


async def setup_rfplayer_test_cfg(
    hass,
    device="abcd",
    automatic_add=False,
    devices: dict[str, dict] | None = None,
    protocols=None,
):
    """Construct a rfplayer config entry."""
    entry_data = create_rfplayer_test_cfg(
        device=device,
        automatic_add=automatic_add,
        devices=devices,
        protocols=protocols,
    )
    mock_entry = MockConfigEntry(
        domain="myrfplayer", unique_id="a_player", data=entry_data
    )
    mock_entry.supports_remove_device = True
    mock_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_entry.entry_id)
    await hass.async_block_till_done()
    await hass.async_start()
    await hass.async_block_till_done()
    return mock_entry


# @pytest.fixture(autouse=True)
# async def transport_mock(hass):
#     """Fixture that make sure all transports are fake."""
#     transport = Mock(spec=RFXtrxTransport)
#     with (
#         patch("RFXtrx.PySerialTransport", new=transport),
#         patch("RFXtrx.PyNetworkTransport", transport),
#     ):
#         yield transport


# @pytest.fixture(autouse=True)
# async def connect_mock(hass):
#     """Fixture that make sure connect class is mocked."""
#     with patch("RFXtrx.Connect") as connect:
#         yield connect


# @pytest.fixture(autouse=True, name="rfxtrx")
# def rfxtrx_fixture(hass, connect_mock):
#     """Fixture that cleans up threads from integration."""

#     rfx = Mock(spec=Connect)

#     def _init(transport, event_callback=None, modes=None):
#         rfx.event_callback = event_callback
#         rfx.transport = transport
#         return rfx

#     connect_mock.side_effect = _init

#     async def _signal_event(packet_id):
#         event = rfxtrx.get_rfx_object(packet_id)
#         await hass.async_add_executor_job(
#             rfx.event_callback,
#             event,
#         )

#         await hass.async_block_till_done()
#         await hass.async_block_till_done()
#         return event

#     rfx.signal = _signal_event

#     return rfx


# @pytest.fixture(name="rfxtrx_automatic")
# async def rfxtrx_automatic_fixture(hass, rfxtrx):
#     """Fixture that starts up with automatic additions."""
#     await setup_rfx_test_cfg(hass, automatic_add=True, devices={})
#     return rfxtrx


# @pytest.fixture
# async def timestep(hass):
#     """Step system time forward."""

#     with freeze_time(utcnow()) as frozen_time:

#         async def delay(seconds):
#             """Trigger delay in system."""
#             frozen_time.tick(delta=seconds)
#             async_fire_time_changed(hass)
#             await hass.async_block_till_done()

#         yield delay
