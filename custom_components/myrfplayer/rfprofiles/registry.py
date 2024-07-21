"""RfPlayer device profile registry."""

from dataclasses import dataclass
from enum import StrEnum
import functools

from jsonpath_ng import parse

from custom_components.myrfplayer.rfplayerlib.protocol import JsonPacketType
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import Platform

RfDeviceClass = SensorDeviceClass | BinarySensorDeviceClass


class EventDataType(StrEnum):
    """Data type for event values."""

    TEMPERATURE = "temperature"
    HUMIDITY = "humidity"
    PRESSURE = "pressure"
    RF_LEVEL = "rf_level"


@dataclass
class BaseValueConfig:
    """Base value extractor."""

    bit_mask: int | None
    bit_offset: int | None
    factor: float | None
    map: dict[str, str] | None

    def _convert(self, value: str) -> str:
        """Convert a raw value."""

        result = value
        if self.bit_mask:
            result = str(int(result) & self.bit_mask)
        if self.bit_offset:
            result = str(int(result) >> self.bit_offset)
        if self.factor:
            result = str(float(result) * self.factor)
        if self.map:
            result = self.map.get(result, "undefined")
        return result


@dataclass
class JsonValueConfig(BaseValueConfig):
    """Generic json value extraction configuration."""

    info_type: str
    json_path: str

    def get_value(self, raw_packet: JsonPacketType) -> str | None:
        """Extract value from json packet type."""

        if raw_packet["frame"]["header"]["infoType"] == self.info_type:
            expr = parse(self.json_path)
            first_match = next(expr.find(raw_packet), None)
            if first_match:
                return self._convert(first_match.value)
        return None


@dataclass
class PlatformConfig:
    """Base class for all platform configurations."""

    device_class: str
    unit: str | None


@dataclass
class SensorProfileConfig(PlatformConfig):
    """Sensor platform configuration."""

    sensor: JsonValueConfig


@dataclass
class ClimateProfileConfig(PlatformConfig):
    """Climate platform configuration."""

    sensor: JsonValueConfig


@dataclass
class CoverProfileConfig(PlatformConfig):
    """Climate platform configuration."""

    position: JsonValueConfig | None
    open: str
    close: str


@dataclass
class LightProfileConfig(PlatformConfig):
    """Climate platform configuration."""

    status: JsonValueConfig
    level: JsonValueConfig | None
    turn_on: str
    turn_off: str
    set_level: str


@dataclass
class DeviceProfile:
    """Device profile configuration."""

    platforms: dict[Platform, dict[str, PlatformConfig]]


class ProfileRegistry:
    """Registry to store RF device profiles."""

    def __init__(self):
        """Create a new registry."""
        self._registry: dict[str, DeviceProfile] = {}

    def register_profile(self, name: str, profile: DeviceProfile) -> None:
        """Add a new device profile into the registry."""

        self._registry[name] = profile

    def unregister_profile(self, name: str) -> None:
        """Remove a device profile from the registry."""

        self._registry.pop(name)

    def get_profile(self, name: str) -> DeviceProfile | None:
        """Get a device profile by name."""

        return self._registry.get(name)

    def list_profile_names(self) -> list[str]:
        """Return the list of registered profile names."""

        return list(self._registry.keys())


@functools.lru_cache(maxsize=1)
def get_profile_registry() -> ProfileRegistry:
    """Get the profile registry singleton."""
    return ProfileRegistry()
