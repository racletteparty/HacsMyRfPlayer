"""Unit tests for rfplayer client."""

from typing import cast
from unittest.mock import Mock

import pytest

from custom_components.myrfplayer.rfplayerlib import RfPlayerClient, RfPlayerException
from custom_components.myrfplayer.rfplayerlib.protocol import RfplayerProtocol


@pytest.mark.asyncio
async def test_connect(
    test_client: RfPlayerClient,
    test_protocol: RfplayerProtocol,
    serial_connection_mock: Mock,
):
    """Test connection."""

    # GIVEN
    # test_client

    # WHEN
    await test_client.connect()

    # THEN
    assert test_client.protocol == test_protocol
    assert test_client.connected
    serial_connection_mock.assert_called_once()


@pytest.mark.asyncio
async def test_receiver_protocols(
    test_client: RfPlayerClient,
    test_protocol: RfplayerProtocol,
    serial_connection_mock: Mock,
):
    """Test connection."""

    # GIVEN
    # test_client

    # WHEN
    await test_client.connect()

    # THEN
    protocol_factory = serial_connection_mock.call_args[0][1]
    protocol = protocol_factory()
    assert "RECEIVER -* +X2D +RTS" in protocol.init_script


@pytest.mark.asyncio
async def test_send_command_connected(
    test_client: RfPlayerClient, test_protocol: RfplayerProtocol
):
    """Test send command."""

    # GIVEN
    await test_client.connect()

    # WHEN
    body = "FORMAT JSON"
    test_client.send_raw_command(body)

    # THEN
    tr = cast(Mock, test_protocol.transport)
    tr.write.assert_called_once_with(b"ZIA++FORMAT JSON\n\r")


def test_send_command_disconnected(test_client: RfPlayerClient):
    """Test send command."""

    # GIVEN
    assert not test_client.connected

    with pytest.raises(RfPlayerException):
        # WHEN
        test_client.send_raw_command("")

        # THEN raise
