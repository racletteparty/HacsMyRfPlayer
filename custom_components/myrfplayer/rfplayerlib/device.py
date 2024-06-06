"""RfPlayer device info extraction."""

from collections.abc import Callable
from dataclasses import dataclass
import logging
from typing import Any

from .protocol import (
    JsonInfo,
    JsonPacketType,
    RfPlayerEventInfo,
    RfPlayerRawEvent,
    SimpleInfo,
    SimplePacketType,
)

_LOGGER = logging.getLogger(__name__)

UNKNOWN_INFO = "unknown"
GATEWAY_PROTOCOL = "gateway"
GATEWAY_DEVICE = "gateway"


@dataclass
class RfDeviceId:
    """Identifiers of a RF device or the RfPlayer gateway itself."""

    protocol: str
    address: str
    group_id: str | None
    model: str | None

    @property
    def device_id(self) -> str:
        """Build a unique device id for the device."""

        if self.group_id is not None:
            return f"{self.protocol}-{self.group_id}:{self.address}"
        return f"{self.protocol}-{self.address}"


@dataclass
class RfDeviceEvent:
    """Device-oriented event after processing a raw RfPlayer event."""

    device: RfDeviceId
    data: RfPlayerRawEvent

    @property
    def device_id(self):
        """Get device id."""

        return self.device.device_id

    @property
    def info_type(self) -> int:
        """Get info type."""

        if isinstance(self.data, JsonPacketType):
            return int(self.data["infoType"])

        return -1

    @property
    def infos(self) -> RfPlayerEventInfo:
        """Get infos for the associated info type."""

        if isinstance(self.data, JsonPacketType):
            return JsonInfo(self.data["infos"])

        return SimpleInfo(self.data)


@dataclass
class RfDeviceEventAdapter:
    """Extract RF device information from a raw RfPlayer event."""

    id: str
    device_event_callback: Callable[[RfDeviceEvent], None]

    def raw_event_callback(self, raw_packet: RfPlayerRawEvent):
        """Convert raw RfPlayer event to RF Device event."""

        if isinstance(raw_packet, SimplePacketType):
            self.device_event_callback(self._simple_packet_to_device_event(raw_packet))
        elif isinstance(raw_packet, JsonPacketType):
            self.device_event_callback(self._json_packet_to_device_event(raw_packet))
        else:
            _LOGGER.warning("Unsupported packet type %s", type(raw_packet).__name__)

    def _simple_packet_to_device_event(
        self, raw_packet: SimplePacketType
    ) -> RfDeviceEvent:
        device = RfDeviceId(
            protocol=GATEWAY_PROTOCOL,
            address=self.id,
            group_id=None,
            model=GATEWAY_DEVICE,
        )
        return RfDeviceEvent(device=device, data=SimplePacketType(raw_packet))

    def _json_packet_to_device_event(
        self, json_packet: JsonPacketType
    ) -> RfDeviceEvent:
        device = self._parse_json_device(json_packet)
        return RfDeviceEvent(device=device, data=json_packet)

    def _convert_raw_model(self, raw_model: str) -> str:
        if raw_model.lower() in ["on", "off"]:
            return "switch"

        return raw_model

    def _get_model(self, infos: dict[str, Any]) -> str:
        for key in ["id_PHYMeaning", "subTypeMeaning"]:
            if key in infos:
                return self._convert_raw_model(infos[key])
        return UNKNOWN_INFO

    def _get_address(self, infos: dict[str, Any]) -> str:
        for key in ["id", "id_channel", "adr_channel"]:
            if key in infos:
                return infos[key]
        return UNKNOWN_INFO

    def _parse_json_device(self, json_packet: dict[str, Any]) -> RfDeviceId:
        header = json_packet["frame"]["header"]
        infos = json_packet["frame"]["infos"]
        protocol = header["protocolMeaning"]
        return RfDeviceId(
            protocol=protocol,
            address=self._get_address(infos),
            group_id=None,
            model=self._get_model(infos),
        )
