"""Unit tests for rfplayer client."""

import json
from unittest.mock import Mock, call


def test_init_script(test_protocol):
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


def test_received_json_single(test_protocol):
    # GIVEN
    body = '{"foo": "bar"}'

    # WHEN
    test_protocol.data_received(f"ZIA33{body}\n\r".encode())

    # THEN
    cb: Mock = test_protocol.event_callback
    cb.assert_called_once_with(json.loads(body))


def test_received_json_multiple(test_protocol):
    # GIVEN
    bodies = ['{"foo1": "bar1"}', '{"foo2": "bar2"}']
    payload = ""

    for body in bodies:
        payload += f"ZIA33{body}\n\r"

    # WHEN
    test_protocol.data_received(payload.encode())

    # THEN
    cb: Mock = test_protocol.event_callback
    cb.assert_has_calls([call(json.loads(bodies[0])), call(json.loads(bodies[1]))])


def test_received_simple_single(test_protocol):
    body = "Hello world!"

    test_protocol.data_received(f"ZIA--{body}\n\r".encode())

    cb: Mock = test_protocol.event_callback
    cb.assert_called_once_with(body)


def test_received_incomplete(test_protocol):
    bodies = ['{"foo1": "bar1"}', '{"foo2": "bar2"}']

    test_protocol.data_received(f"ZIA33{bodies[0]}\n\r\n\rZIA33".encode())
    test_protocol.data_received(f"{bodies[1]}\n\r".encode())

    cb: Mock = test_protocol.event_callback
    cb.assert_has_calls([call(json.loads(bodies[0])), call(json.loads(bodies[1]))])


def test_received_strip(test_protocol):
    body = '{"foo": "bar"}'

    test_protocol.data_received(f"\r\0 ZIA33{body}\t\n\r".encode())

    cb: Mock = test_protocol.event_callback
    cb.assert_called_once_with(json.loads(body))


def test_received_invalid(test_protocol):
    test_protocol.data_received(b"ZIA33\n\r")

    cb: Mock = test_protocol.event_callback
    cb.assert_not_called()


def test_send(test_protocol):
    body = "FORMAT JSON"
    test_protocol.send_raw_packet(body)

    tr: Mock = test_protocol.transport
    tr.write.assert_called_once_with(f"ZIA++{body}\n\r".encode())


def test_connection_lost_error(test_protocol):
    ex = Exception()
    test_protocol.connection_lost(ex)

    tr: Mock = test_protocol.disconnect_callback
    tr.assert_called_once_with(ex)


def test_connection_lost_closed(test_protocol):
    test_protocol.connection_lost(None)

    tr: Mock = test_protocol.disconnect_callback
    tr.assert_called_once_with(None)
