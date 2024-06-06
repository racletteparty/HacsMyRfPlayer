"""Async RfPlayer client."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import cast

from serial import SerialException
from serial_asyncio import create_serial_connection

from .device import RfDeviceEvent, RfDeviceEventAdapter
from .protocol import RfplayerProtocol

RECEIVER_MODES = [
    "*",
    "X10",
    "RTS",
    "VISONIC",
    "BLYSS",
    "CHACON",
    "OREGONV1",
    "OREGONV2",
    "OREGONV3/OWL",
    "DOMIA",
    "X2D",
    "KD101",
    "PARROT",
    "TIC",
    "FS20",
    "JAMMING",
    "EDISIO",
]


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
    receiver_protocols: list[str] | None = None
    _protocol: RfplayerProtocol | None = None

    async def connect(self):
        """Open connection with RfPlayer gateway."""

        adapter = RfDeviceEventAdapter(
            id=self.port, device_event_callback=self.event_callback
        )

        protocol_factory = partial(
            RfplayerProtocol,
            id=self.port,
            loop=self.loop,
            event_callback=adapter.raw_event_callback,
            disconnect_callback=self._disconnect_callback_internal,
            init_script=self._receiver_script(),
        )
        try:
            (_, protocol) = await create_serial_connection(
                self.loop, protocol_factory, self.port, self.baud
            )
        except (SerialException, OSError) as err:
            raise RfPlayerException("Failed to create serial connection") from err
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

    @property
    def connected(self) -> bool:
        """True if the client is connected."""

        return self._protocol is not None

    @property
    def protocol(self):
        """The underlying asyncio protocol."""

        return self._protocol

    def _disconnect_callback_internal(self):
        self.close()
        self.disconnect_callback()

    def _receiver_script(self) -> list[str]:
        if self.receiver_protocols:
            return [f"RECEIVER -* +{' +'.join(self.receiver_protocols)}"]

        return []
