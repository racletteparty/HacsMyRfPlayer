"""RfPlayer device profile registry."""

from enum import StrEnum
import functools
import json
import logging
import os
from pathlib import Path
import re

from jsonpath_ng.ext import parse
from pydantic import BaseConfig, BaseModel, parse_obj_as
import yaml

from custom_components.myrfplayer.rfplayerlib.protocol import RfPlayerEventData
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import STATE_CLOSED, STATE_OPEN, EntityCategory, Platform
from homeassistant.core import HomeAssistant

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

    def get_value(self, event_data: RfPlayerEventData) -> str | None:
        """Extract value from json event."""
        return self._find_value(event_data, self.value_path)

    def get_unit(self, event_data: RfPlayerEventData) -> str | None:
        """Extract value from json event."""
        return self._find_value(event_data, self.unit_path) if self.unit_path else None

    def _find_value(self, event_data: RfPlayerEventData, json_path: str) -> str | None:
        """Extract value from json event."""

        expr = parse(json_path)
        all_match = expr.find(event_data)
        if all_match:
            return self._convert(all_match[0].value)
        return None


class RfpPlatformConfig(BaseModel):
    """Base class for all platform configurations."""

    name: str
    device_class: str | None
    category: EntityCategory | None
    unit: str | None

    class Config(BaseConfig):
        """Enable private properties for map caching."""

        underscore_attrs_are_private = True


class RfpSensorConfig(RfpPlatformConfig):
    """Sensor platform configuration."""

    state: JsonValueConfig
    state_class: str | None

    def event_unit(self, event_data: RfPlayerEventData | None) -> str | None:
        """Return unit from event of static unit."""
        if event_data:
            return self.state.get_unit(event_data) or self.unit
        return self.unit


class ClimateEventTypes(StrEnum):
    """Supported event value selection."""

    STATE = "state"
    PRESET_MODE = "preset_mode"
    ALL = "all"


class RfpClimateConfig(RfpPlatformConfig):
    """Climate platform configuration."""

    event_code: JsonValueConfig
    event_types: dict[str, ClimateEventTypes]
    state: JsonValueConfig
    preset_mode: JsonValueConfig
    preset_modes: dict[str, str]
    cmd_turn_on: str
    cmd_turn_off: str
    cmd_set_mode: str | None
    _preset_modes_cache: dict[str, str] | None = None

    def make_cmd_turn_on(self, **kwargs):
        """Format the turn on command with address."""
        assert self.cmd_turn_on
        kwargs["preset_mode"] = self._mode_to_code(kwargs["preset_mode"])
        return self.cmd_turn_on.format(**kwargs)

    def make_cmd_turn_off(self, **kwargs):
        """Format the turn off command with address."""
        assert self.cmd_turn_off
        kwargs["preset_mode"] = self._mode_to_code(kwargs["preset_mode"])
        return self.cmd_turn_off.format(**kwargs)

    def make_cmd_set_mode(self, **kwargs):
        """Format the set mode command with address and mode."""
        assert self.cmd_set_mode
        kwargs["preset_mode"] = self._mode_to_code(kwargs["preset_mode"])
        return self.cmd_set_mode.format(**kwargs)

    def _mode_to_code(self, mode: str | None):
        if not self._preset_modes_cache:
            self._preset_modes_cache = {value: key for (key, value) in self.preset_modes.items()}
        return self._preset_modes_cache[mode] if mode else list(self._preset_modes_cache.values())[0]


class CoverState(StrEnum):
    """Allowed cover states."""

    OPEN = STATE_OPEN
    CLOSED = STATE_CLOSED


class RfpCoverConfig(RfpPlatformConfig):
    """Climate platform configuration."""

    state: JsonValueConfig | None
    states: dict[str, CoverState]
    cmd_open: str
    cmd_close: str
    cmd_stop: str | None

    def make_cmd_open(self, **kwargs):
        """Format the open command with address."""
        assert self.cmd_open
        return self.cmd_open.format(**kwargs)

    def make_cmd_close(self, **kwargs):
        """Format the close command with address."""
        assert self.cmd_close
        return self.cmd_close.format(**kwargs)

    def make_cmd_stop(self, **kwargs):
        """Format the close command with address."""
        assert self.cmd_stop
        return self.cmd_stop.format(**kwargs)


class RfpSwitchConfig(RfpPlatformConfig):
    """Climate platform configuration."""

    status: JsonValueConfig
    cmd_turn_on: str
    cmd_turn_off: str

    def make_cmd_turn_on(self, **kwargs):
        """Format the turn on command with address."""
        assert self.cmd_turn_on
        return self.cmd_turn_on.format(**kwargs)

    def make_cmd_turn_off(self, **kwargs):
        """Format the turn off command with address."""
        assert self.cmd_turn_off
        return self.cmd_turn_off.format(**kwargs)


class RfpLightConfig(RfpSwitchConfig):
    """Climate platform configuration."""

    cmd_set_level: str | None

    def make_cmd_set_level(self, **kwargs):
        """Format the set level command with address and brightness."""
        assert self.cmd_set_level
        return self.cmd_set_level.format(**kwargs)


AnyRfpPlatformConfig = RfpClimateConfig | RfpSensorConfig | RfpCoverConfig | RfpSwitchConfig | RfpLightConfig


class RfpPlatformConfigMap(BaseModel):
    """Explicit plaform config map.

    Remove deserialization ambiguity with union and avoid using pydantic discriminator.
    """

    binary_sensor: list[RfpSensorConfig] | None
    climate: list[RfpClimateConfig] | None
    cover: list[RfpCoverConfig] | None
    light: list[RfpLightConfig] | None
    sensor: list[RfpSensorConfig] | None
    switch: list[RfpSwitchConfig] | None

    def get(self, platform: Platform) -> list[AnyRfpPlatformConfig]:
        """Return the config for the given platform."""
        return vars(self).get(platform, [])


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
    platforms: RfpPlatformConfigMap


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

    def get_profile_name_from_event(self, event_data: RfPlayerEventData) -> str | None:
        """Get a plaform config matching an event."""
        matching_profiles = (entry for entry in self._registry if self._event_is_matching(event_data, entry))

        profile = next(matching_profiles, None)

        if not profile:
            _LOGGER.warning("No matching profile for event %s", json.dumps(event_data))
            return None
        return profile.name

    def get_platform_config(self, profile_name: str | None, platform: Platform) -> list[AnyRfpPlatformConfig]:
        """Get a plaform config matching an event."""
        platform_config: list[AnyRfpPlatformConfig] = []

        if not profile_name:
            _LOGGER.debug("No profile name provided")
            return platform_config

        matching_profiles = (entry for entry in self._registry if entry.name == profile_name)

        profile = next(matching_profiles, None)

        if not profile:
            _LOGGER.warning("Profile name %s not supported", profile_name)
        else:
            platform_config = profile.platforms.get(platform)
            if not platform_config:
                _LOGGER.debug("Platform %s not supported by profile %s", platform, profile.name)

        return platform_config

    def get_profile_names(self) -> list[str]:
        """Get the list of available profile names."""
        return [item.name for item in self._registry]

    def _event_is_matching(self, event_data: RfPlayerEventData, profile: RfpDeviceProfile):
        if not isinstance(event_data, RfPlayerEventData | dict):
            _LOGGER.debug("not matching: not a JSON RfPlayer event")
            return False

        m = profile.match
        if m.protocol:
            protocol = event_data["frame"]["header"]["protocolMeaning"]
            if not re.match(m.protocol, protocol):
                _LOGGER.debug(
                    "profile %s not matching: expected protocol %s, actual %s",
                    profile.name,
                    m.protocol,
                    protocol,
                )
                return False
        info_type = event_data["frame"]["header"]["infoType"]
        if info_type != m.info_type:
            _LOGGER.debug("not matching: expected info type %s, actual %s", m.info_type, info_type)
            return False
        if m.sub_type:
            sub_type = event_data["frame"]["infos"]["subType"]
            if sub_type != m.sub_type:
                _LOGGER.debug(
                    "not matching: expected sub type %s, actual %s",
                    m.sub_type,
                    sub_type,
                )
                return False
        if m.id_phy:
            id_phy = event_data["frame"]["infos"]["id_PHY"]
            if not re.match(m.id_phy, id_phy):
                _LOGGER.debug("not matching: expected id phy %s, actual %s", m.id_phy, id_phy)
                return False
        return True


@functools.lru_cache(maxsize=1)
def _get_profile_registry() -> ProfileRegistry:
    """Get the profile registry singleton."""
    module_path = Path(os.path.abspath(__file__)).parent
    return ProfileRegistry(module_path / "device-profiles.yaml")


async def async_get_profile_registry(hass: HomeAssistant) -> ProfileRegistry:
    """Asynchronously load the RF device profile registry."""
    return await hass.async_add_executor_job(_get_profile_registry)