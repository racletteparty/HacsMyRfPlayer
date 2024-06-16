"""Async RfPlayer client."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import cast

from serial_asyncio import create_serial_connection

from .device import RfDeviceEvent, RfDeviceEventAdapter
from .protocol import RfplayerProtocol


class RfPlayerException(Exception):
    """Generic RfPlayer exception."""


@dataclass
class RfPlayerClient:
    """Client to RfPlayer gateway."""

    event_callback: Callable[[RfDeviceEvent], None]
    disconnect_callback: Callable[[Exception | None], None]
    loop: asyncio.AbstractEventLoop
    port: str = "/dev/ttyUSB0"
    baud: int = 115200
    _protocol: RfplayerProtocol = None

    async def connect(self):
        """Open connection with RfPlayer gateway."""

        adapter = RfDeviceEventAdapter(self.event_callback)

        protocol_factory = partial(
            RfplayerProtocol,
            id=self.port,
            loop=self.loop,
            event_callback=adapter.raw_event_callback,
            disconnect_callback=self.disconnect_callback,
        )
        (_, protocol) = await create_serial_connection(
            self.loop, protocol_factory, self.port, self.baud
        )
        self._protocol = cast(RfplayerProtocol, protocol)

    def close(self):
        """Close connection if open."""

        if self._protocol and self._protocol.transport:
            self._protocol.transport.close()
            self._protocol = None

    def send_raw_command(self, command: str):
        """Send a command raw command."""

        if not self._protocol or not self._protocol.transport:
            raise RfPlayerException("Not connected")

        return self._protocol.send_raw_packet(command)
