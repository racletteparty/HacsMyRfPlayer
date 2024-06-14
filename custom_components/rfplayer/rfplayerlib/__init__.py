"""RfPlayer client."""

"""Asyncio protocol implementation of RFplayer."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
import json
import logging
from typing import Any, Optional, Union, cast

from serial_asyncio import create_serial_connection

_LOGGER = logging.getLogger(__name__)

RESPONSE_TIMEOUT = 5.0
END_OF_LINE = "\n\r"
PACKET_HEADER_LEN = 5
MINIMUM_SCRIPT = ["FORMAT JSON", "STATUS JSON"]
UNKNOWN_INFO = "unknown"
GATEWAY_PROTOCOL = "gateway"
GATEWAY_DEVICE = "gateway"


@dataclass
class RfPlayerDevice:
    """Representation of a RF device or the RfPlayer gateway itself."""

    protocol: str
    device_id: str
    device_type: str
    info_type: str | None

    @property
    def unique_id(self) -> str:
        """Build a unique id for the device."""

        return f"{self.protocol}_{self.device_id}"

    def identifiers(self) -> str:
        """Build a list of identifiers for the device."""

        [(k, v) for k, v in dict.items()]


class RfPlayerException(Exception):
    """Generic RfPlayer exception."""


class JsonPacketType(dict):
    """RfPlayer JSON packet type."""


class SimplePacketType(str):
    """RfPlayer simple string packet type."""

    __slots__ = ()


@dataclass
class RfPlayerEvent:
    """Representation of a received RF event."""

    device: RfPlayerDevice
    data: Union[JsonPacketType | SimplePacketType]


def _valid_packet(line: str):
    return len(line) > PACKET_HEADER_LEN


class RfplayerProtocol(asyncio.Protocol):
    """Manage low level rfplayer protocol."""

    def __init__(
        self,
        id: str,
        loop: asyncio.AbstractEventLoop,
        event_callback: Callable[[RfPlayerEvent], None],
        disconnect_callback: Callable[[Exception | None], None],
        init_script: Optional[list[str]] = None,
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
            self.event_callback(self._json_packet_to_event(body))
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

    def _simple_packet_to_event(self, raw_packet: str) -> RfPlayerEvent:
        device = RfPlayerDevice(
            protocol=GATEWAY_PROTOCOL,
            device_id=self.id,
            device_type=GATEWAY_DEVICE,
        )
        return RfPlayerEvent(device=device, data=SimplePacketType(raw_packet))

    def _json_packet_to_event(self, raw_packet: str) -> RfPlayerEvent:
        json_packet = json.loads(raw_packet)
        device = self._parse_json_device(json_packet)
        return RfPlayerEvent(device=device, data=JsonPacketType(json_packet))

    def _parse_json_device(self, json_packet: dict[Any, Any]) -> RfPlayerDevice:
        header = json_packet["frame"]["header"]
        infos = json_packet["frame"]["infos"]
        device_id = UNKNOWN_INFO
        for key in ["id", "id_channel", "adr_channel"]:
            if key in infos:
                device_id = infos[key]
        device_type = UNKNOWN_INFO
        for key in ["id_PHYMeaning", "subTypeMeaning"]:
            if key in infos:
                device_type = infos[key]
        protocol = header["protocolMeaning"]
        info_type = header["infoType"]
        return RfPlayerDevice(
            protocol=protocol,
            device_id=device_id,
            device_type=device_type,
            info_type=info_type,
        )


@dataclass
class RfPlayerClient:
    """Client to RfPlayer gateway."""

    event_callback: Callable[[RfPlayerEvent], None]
    disconnect_callback: Callable[[Exception | None], None]
    loop: asyncio.AbstractEventLoop
    port: str = "/dev/ttyUSB0"
    baud: int = 115200
    protocol: RfplayerProtocol = None  # FIXME should be private

    async def connect(self):
        """Open connection with RfPlayer gateway."""

        protocol_factory = partial(
            RfplayerProtocol,
            id=self.port,
            loop=self.loop,
            event_callback=self.event_callback,
            disconnect_callback=self.disconnect_callback,
        )
        (_, protocol) = await create_serial_connection(
            self.loop, protocol_factory, self.port, self.baud
        )
        self.protocol = cast(RfplayerProtocol, protocol)

    def send_raw_command(self, command: str):
        """Send a command raw command."""

        if not self.protocol or not self.protocol.transport:
            raise RfPlayerException("Not connected")

        return self.protocol.send_raw_packet(command)
