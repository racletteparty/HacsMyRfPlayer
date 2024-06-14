"""Unit tests for rfplayer client."""

import json
from unittest.mock import Mock, call


def test_init_script(new_protocol):
    # GIVEN
    assert new_protocol.init_script == [
        "FORMAT JSON",
        "STATUS JSON",
        "LEDACTIVITY 0",
        "JAMMING 10",
    ]
    transport = Mock()

    # WHEN
    new_protocol.connection_made(transport)

    transport.write.assert_has_calls(
        [
            call(b"ZIA++FORMAT JSON\n\r"),
            call(b"ZIA++STATUS JSON\n\r"),
            call(b"ZIA++LEDACTIVITY 0\n\r"),
            call(b"ZIA++JAMMING 10\n\r"),
        ]
    )


def test_received_json_single(new_protocol):
    # GIVEN
    body = '{"foo": "bar"}'

    # WHEN
    new_protocol.data_received(f"ZIA33{body}\n\r".encode())

    # THEN
    cb: Mock = new_protocol.event_callback
    cb.assert_called_once_with(json.loads(body))


def test_received_json_multiple(new_protocol):
    # GIVEN
    bodies = ['{"foo1": "bar1"}', '{"foo2": "bar2"}']
    payload = ""

    for body in bodies:
        payload += f"ZIA33{body}\n\r"

    # WHEN
    new_protocol.data_received(payload.encode())

    # THEN
    cb: Mock = new_protocol.event_callback
    cb.assert_has_calls([call(json.loads(bodies[0])), call(json.loads(bodies[1]))])


def test_received_simple_single(new_protocol):
    body = "Hello world!"

    new_protocol.data_received(f"ZIA--{body}\n\r".encode())

    cb: Mock = new_protocol.event_callback
    cb.assert_called_once_with(body)


def test_received_incomplete(new_protocol):
    bodies = ['{"foo1": "bar1"}', '{"foo2": "bar2"}']

    new_protocol.data_received(f"ZIA33{bodies[0]}\n\r\n\rZIA33".encode())
    new_protocol.data_received(f"{bodies[1]}\n\r".encode())

    cb: Mock = new_protocol.event_callback
    cb.assert_has_calls([call(json.loads(bodies[0])), call(json.loads(bodies[1]))])


def test_received_strip(new_protocol):
    body = '{"foo": "bar"}'

    new_protocol.data_received(f"\r\0 ZIA33{body}\t\n\r".encode())

    cb: Mock = new_protocol.event_callback
    cb.assert_called_once_with(json.loads(body))


def test_received_invalid(new_protocol):
    new_protocol.data_received(b"ZIA33\n\r")

    cb: Mock = new_protocol.event_callback
    cb.assert_not_called()


def test_send(new_protocol):
    body = "FORMAT JSON"
    new_protocol.send_raw_packet(body)

    tr: Mock = new_protocol.transport
    tr.write.assert_called_once_with(f"ZIA++{body}\n\r".encode())


def test_connection_lost_error(new_protocol):
    ex = Exception()
    new_protocol.connection_lost(ex)

    tr: Mock = new_protocol.disconnect_callback
    tr.assert_called_once_with(ex)


def test_connection_lost_closed(new_protocol):
    new_protocol.connection_lost(None)

    tr: Mock = new_protocol.disconnect_callback
    tr.assert_called_once_with(None)
