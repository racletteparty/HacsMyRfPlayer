"""RfPlayer device profile registry."""

import functools
import json
import logging
import os
from pathlib import Path
import re

from jsonpath_ng.ext import parse
from pydantic import BaseModel, parse_obj_as
import yaml

from custom_components.myrfplayer.rfplayerlib.protocol import (
    JsonPacketType,
    RfPlayerRawEvent,
)
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import Platform

RfDeviceClass = SensorDeviceClass | BinarySensorDeviceClass
_LOGGER = logging.getLogger(__name__)


class BaseValueConfig(BaseModel):
    """Base value extractor."""

    bit_mask: int | None
    bit_offset: int | None
    map: dict[str, str] | None
    factor: float | None

    def _convert(self, value: str) -> str:
        """Convert a raw value."""

        result = value
        if self.bit_mask:
            result = str(int(result) & self.bit_mask)
        if self.bit_offset:
            result = str(int(result) >> self.bit_offset)
        if self.map:
            result = self.map.get(result, "undefined")
        if self.factor:
            result = str(float(result) * self.factor)
        return result


class JsonValueConfig(BaseValueConfig):
    """Generic json value extraction configuration."""

    value_path: str
    unit_path: str | None

    def get_value(self, raw_packet: JsonPacketType) -> str | None:
        """Extract value from json packet type."""
        return self._find_value(raw_packet, self.value_path)

    def get_unit(self, raw_packet: JsonPacketType) -> str | None:
        """Extract value from json packet type."""
        return self._find_value(raw_packet, self.unit_path) if self.unit_path else None

    def _find_value(self, raw_packet: JsonPacketType, json_path: str) -> str | None:
        """Extract value from json packet type."""

        expr = parse(json_path)
        all_match = expr.find(raw_packet)
        if all_match:
            return self._convert(all_match[0].value)
        return None


class RfpPlatformConfig(BaseModel):
    """Base class for all platform configurations."""

    name: str
    device_class: str | None
    unit: str | None


class RfpSensorConfig(RfpPlatformConfig):
    """Sensor platform configuration."""

    config: JsonValueConfig


class RfpClimateConfig(RfpPlatformConfig):
    """Climate platform configuration."""

    config: JsonValueConfig


class RfpCoverConfig(RfpPlatformConfig):
    """Climate platform configuration."""

    config_position: JsonValueConfig | None
    cmd_open: str
    cmd_close: str


class RfpLightConfig(RfpPlatformConfig):
    """Climate platform configuration."""

    config_status: JsonValueConfig
    config_level: JsonValueConfig | None
    cmd_turn_on: str
    cmd_turn_off: str
    cmd_set_level: str | None


AnyRfpPlatformConfig = (
    RfpSensorConfig | RfpClimateConfig | RfpCoverConfig | RfpLightConfig
)


class RfPDeviceMatch(BaseModel):
    """Frame matching rule to detect device."""

    protocol: str | None
    info_type: str
    sub_type: str | None
    id_phy: str | None


class RfpDeviceProfile(BaseModel):
    """Device profile configuration."""

    name: str
    match: RfPDeviceMatch
    platforms: dict[Platform, list[AnyRfpPlatformConfig]]


class ProfileRegistry:
    """Registry to store RF device profiles."""

    def __init__(self, filename: Path):
        """Create a new registry."""
        self._registry: list[RfpDeviceProfile] = []
        with open(filename, encoding="utf-8") as f:
            self.register_profiles(f.read())

    def register_profiles(self, content: str) -> None:
        """Add new yaml device profiles into the registry."""

        obj = yaml.safe_load(content)
        items = parse_obj_as(list[RfpDeviceProfile], obj)
        self._registry.extend(items)

    def get_platform_config(
        self, raw_packet: RfPlayerRawEvent, platform: Platform
    ) -> list[AnyRfpPlatformConfig]:
        """Get a device profile by name."""
        platform_config: list[AnyRfpPlatformConfig] = []

        matching_profiles = (
            entry for entry in self._registry if self._is_matching(raw_packet, entry)
        )

        profile = next(matching_profiles, None)

        if not profile:
            _LOGGER.debug("No matching profile for packet %s", json.dumps(raw_packet))
        else:
            platform_config = profile.platforms.get(platform, [])
            if not platform_config:
                _LOGGER.debug(
                    "Platform %s not supported by profile %s", platform, profile.name
                )

        return platform_config

    def _is_matching(self, raw_packet: RfPlayerRawEvent, profile: RfpDeviceProfile):
        if not isinstance(raw_packet, (JsonPacketType, dict)):
            _LOGGER.debug("not matching: not a JSON packet")
            return False

        m = profile.match
        if m.protocol:
            protocol = raw_packet["frame"]["header"]["protocolMeaning"]
            if not re.match(m.protocol, protocol):
                _LOGGER.debug(
                    "not matching: expected protocol %s, actual %s",
                    m.protocol,
                    protocol,
                )
                return False
        info_type = raw_packet["frame"]["header"]["infoType"]
        if info_type != m.info_type:
            _LOGGER.debug(
                "not matching: expected info type %s, actual %s", m.info_type, info_type
            )
            return False
        if m.sub_type:
            sub_type = raw_packet["frame"]["infos"]["subType"]
            if sub_type != m.sub_type:
                _LOGGER.debug(
                    "not matching: expected sub type %s, actual %s",
                    m.sub_type,
                    sub_type,
                )
                return False
        if m.id_phy:
            id_phy = raw_packet["frame"]["infos"]["id_PHY"]
            if not re.match(m.id_phy, id_phy):
                _LOGGER.debug(
                    "not matching: expected id phy %s, actual %s", m.id_phy, id_phy
                )
                return False
        return True


@functools.lru_cache(maxsize=1)
def get_profile_registry() -> ProfileRegistry:
    """Get the profile registry singleton."""
    module_path = Path(os.path.abspath(__file__)).parent
    return ProfileRegistry(module_path / "device-profiles.yaml")
