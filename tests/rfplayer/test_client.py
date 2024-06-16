"""Unit tests for rfplayer client."""

from unittest.mock import Mock

import pytest
from pytest_mock import MockerFixture

from custom_components.myrfplayer.rfplayerlib import (
    RfPlayerClient,
    RfPlayerException,
    RfplayerProtocol,
)


@pytest.mark.asyncio
async def test_connect(mocker: MockerFixture):
    """Test connection."""

    event_callback = Mock()
    disconnect_callback = Mock()
    loop = Mock()
    port: str = "/dev/ttyUSB0"
    baud: int = 115200
    protocol: RfplayerProtocol = Mock()

    create_serial_connection = mocker.patch(
        "custom_components.rfplayer.rfplayerlib.client.create_serial_connection",
        return_value=(None, protocol),
    )
    client = RfPlayerClient(
        event_callback=event_callback,
        disconnect_callback=disconnect_callback,
        loop=loop,
        port=port,
        baud=baud,
    )
    await client.connect()

    assert client._protocol == protocol
    create_serial_connection.assert_called_once()


def test_send_command_connected(mocker: MockerFixture):
    """Test send command."""

    client = RfPlayerClient(
        event_callback=Mock(),
        disconnect_callback=Mock(),
        loop=Mock(),
    )
    client._protocol = Mock()

    body = "FORMAT JSON"
    client.send_raw_command(body)

    client._protocol.send_raw_packet.assert_called_once_with(body)


def test_send_command_disconnected(mocker: MockerFixture):
    """Test send command."""

    client = RfPlayerClient(
        event_callback=Mock(),
        disconnect_callback=Mock(),
        loop=Mock(),
    )

    with pytest.raises(RfPlayerException):
        client.send_raw_command("")
