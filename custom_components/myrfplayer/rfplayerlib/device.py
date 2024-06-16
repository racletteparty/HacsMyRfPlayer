"""RfPlayer device info extraction."""

from collections.abc import Callable
from dataclasses import dataclass
import json
import logging

from jsonpath_ng import parse

from .protocol import JsonPacketType, RfPlayerRawEvent, SimplePacketType

_LOGGER = logging.getLogger(__name__)

UNKNOWN_INFO = "unknown"
GATEWAY_PROTOCOL = "gateway"
GATEWAY_DEVICE = "gateway"


@dataclass
class RfDeviceId:
    """Identifiers of a RF device or the RfPlayer gateway itself."""

    protocol: str
    address: str
    device_type: str

    @property
    def device_id(self) -> str:
        """Build a unique device id for the device."""

        return f"{self.protocol}_{self.address}".lower()



class RfDeviceEvent:
    """Device-oriented event after processing a raw RfPlayer event."""

    device: RfDeviceId
    data: RfPlayerRawEvent



@dataclass
class RfDeviceEventAdapter:
    """Extract RF device information from a raw RfPlayer event."""

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
            device_type=GATEWAY_DEVICE,
        )
        return RfDeviceEvent(device=device, data=SimplePacketType(raw_packet))

    def _json_packet_to_device_event(self, raw_packet: JsonPacketType) -> RfDeviceEvent:
        json_packet = json.loads(raw_packet)
        device = self._parse_json_device(json_packet)
        return RfDeviceEvent(device=device, data=JsonPacketType(json_packet))

    def _parse_json_device(self, json_packet: dict) -> RfDeviceId:
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
        # info_type = header["infoType"]
        return RfDeviceId(
            protocol=protocol,
            address=device_id,
            device_type=device_type,
        )
