"""Unit tests for rfplayer client."""

import json
from typing import cast
from unittest.mock import Mock, call

from custom_components.myrfplayer.rfplayerlib.protocol import RfplayerProtocol


def test_init_script(test_protocol: RfplayerProtocol):
    # GIVEN
    assert test_protocol.init_script == [
        "FORMAT JSON",
        "LEDACTIVITY 0",
        "JAMMING 10",
    ]
    transport = Mock()

    # WHEN
    test_protocol.connection_made(transport)

    transport.write.assert_has_calls(
        [
            call(b"ZIA++FORMAT JSON\n\r"),
            call(b"ZIA++LEDACTIVITY 0\n\r"),
            call(b"ZIA++JAMMING 10\n\r"),
        ]
    )


def test_received_json_single(test_protocol: RfplayerProtocol):
    # GIVEN
    body = '{"foo": "bar"}'

    # WHEN
    test_protocol.data_received(f"ZIA33{body}\n\r".encode())

    # THEN
    cb = cast(Mock, test_protocol.event_callback)
    cb.assert_called_once_with(json.loads(body))


def test_received_json_multiple(test_protocol: RfplayerProtocol):
    # GIVEN
    bodies = ['{"foo1": "bar1"}', '{"foo2": "bar2"}']
    payload = ""

    for body in bodies:
        payload += f"ZIA33{body}\n\r"

    # WHEN
    test_protocol.data_received(payload.encode())

    # THEN
    cb = cast(Mock, test_protocol.event_callback)
    cb.assert_has_calls([call(json.loads(bodies[0])), call(json.loads(bodies[1]))])


def test_received_simple_single(test_protocol: RfplayerProtocol):
    body = "Hello world!"

    test_protocol.data_received(f"ZIA--{body}\n\r".encode())

    cb = cast(Mock, test_protocol.event_callback)
    cb.assert_called_once_with(body)


def test_received_incomplete(test_protocol: RfplayerProtocol):
    bodies = ['{"foo1": "bar1"}', '{"foo2": "bar2"}']

    test_protocol.data_received(f"ZIA33{bodies[0]}\n\r\n\rZIA33".encode())
    test_protocol.data_received(f"{bodies[1]}\n\r".encode())

    cb = cast(Mock, test_protocol.event_callback)
    cb.assert_has_calls([call(json.loads(bodies[0])), call(json.loads(bodies[1]))])


def test_received_strip(test_protocol: RfplayerProtocol):
    body = '{"foo": "bar"}'

    test_protocol.data_received(f"\r\0 ZIA33{body}\t\n\r".encode())

    cb = cast(Mock, test_protocol.event_callback)
    cb.assert_called_once_with(json.loads(body))


def test_received_invalid(test_protocol: RfplayerProtocol):
    test_protocol.data_received(b"ZIA33\n\r")

    cb = cast(Mock, test_protocol.event_callback)
    cb.assert_not_called()


def test_send(test_protocol: RfplayerProtocol):
    body = "FORMAT JSON"
    test_protocol.send_raw_packet(body)

    tr = cast(Mock, test_protocol.transport)
    tr.write.assert_called_once_with(f"ZIA++{body}\n\r".encode())


def test_connection_lost_error(test_protocol: RfplayerProtocol):
    ex = Exception()
    test_protocol.connection_lost(ex)

    tr = cast(Mock, test_protocol.disconnect_callback)
    tr.assert_called_once_with(ex)


def test_connection_lost_closed(test_protocol: RfplayerProtocol):
    test_protocol.connection_lost(None)

    tr = cast(Mock, test_protocol.disconnect_callback)
    tr.assert_called_once_with(None)
