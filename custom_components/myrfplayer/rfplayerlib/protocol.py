"""Async RfPlayer low-level protocol."""

import asyncio
from collections.abc import Callable
import json
import logging
from typing import cast

_LOGGER = logging.getLogger(__name__)

END_OF_LINE = "\n\r"
PACKET_HEADER_LEN = 5
MINIMUM_SCRIPT = ["FORMAT JSON"]


class JsonPacketType(dict):
    """RfPlayer JSON packet type."""


class JsonInfo(dict):
    """RfPlayer JSON event infos."""


class SimplePacketType(str):
    """RfPlayer simple string packet type."""

    __slots__ = ()


class SimpleInfo(str):
    """RfPlayer simple response."""

    __slots__ = ()


RfPlayerRawEvent = JsonPacketType | SimplePacketType
RfPlayerEventInfo = JsonInfo | SimpleInfo


def _valid_packet(line: str):
    return len(line) > PACKET_HEADER_LEN


class RfplayerProtocol(asyncio.Protocol):
    """Manage low level rfplayer protocol."""

    def __init__(
        self,
        id: str,
        loop: asyncio.AbstractEventLoop,
        event_callback: Callable[[RfPlayerRawEvent], None],
        disconnect_callback: Callable[[Exception | None], None],
        init_script: list[str] | None = None,
    ) -> None:
        """Initialize class."""

        self.id = id
        self.loop = loop
        self.transport: asyncio.WriteTransport | None = None
        self.event_callback = event_callback
        self.disconnect_callback = disconnect_callback
        complete_init_script = list(MINIMUM_SCRIPT)
        complete_init_script.extend(init_script or [])
        self.init_script = complete_init_script
        self.buffer = ""

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        """Just logging for now."""
        self.transport = cast(asyncio.WriteTransport, transport)
        for command in self.init_script:
            self.send_raw_packet(command)

    def data_received(self, data: bytes) -> None:
        """Add incoming data to buffer."""
        try:
            _LOGGER.debug("received data: %s", repr(data))
            decoded_data = data.decode()
        except UnicodeDecodeError:
            invalid_data = data.decode(errors="replace")
            _LOGGER.warning(
                "Error during decode of data, invalid data: %s", invalid_data
            )
        else:
            self.buffer += decoded_data
            self.handle_lines()

    def handle_lines(self) -> None:
        """Assemble incoming data into per-line packets."""
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            line = line.strip("\0 \t\r")
            if _valid_packet(line):
                self.handle_raw_packet(line)
            else:
                _LOGGER.warning("dropping invalid data: %s", line)

    def handle_raw_packet(self, raw_packet: str) -> None:
        """Handle one raw incoming packet."""
        header = raw_packet[0:5]
        body = raw_packet[5:]
        if header == "ZIA--":
            self.event_callback(cast(SimplePacketType, body))
        elif header == "ZIA33":
            self.event_callback(cast(JsonPacketType, json.loads(body)))
        elif header in ["ZIA00", "ZIA11", "ZIA22", "ZIA44", "ZIA66"]:
            _LOGGER.warning("unsupported packet format: %s", header)
            _LOGGER.debug("packet body: %s", body)
        else:
            _LOGGER.warning("dropping invalid packet: %s", raw_packet)

    def send_raw_packet(self, raw_packet: str) -> None:
        """Encode and put packet string onto write buffer."""
        data = bytes(f"ZIA++{raw_packet}{END_OF_LINE}", "utf-8")
        _LOGGER.debug("sending raw packet: %s", repr(data))
        assert self.transport is not None
        self.transport.write(data)

    def connection_lost(self, exc: Exception | None) -> None:
        """Log when connection is closed, if needed call callback."""
        if exc:
            _LOGGER.warning("connection lost due to error %s", exc)
        else:
            _LOGGER.info("connection explicitly closed")
        self.disconnect_callback(exc)
