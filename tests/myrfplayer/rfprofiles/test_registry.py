from custom_components.myrfplayer.rfplayerlib.protocol import JsonPacketType
from custom_components.myrfplayer.rfprofiles.registry import (
    AnyRfpPlatformConfig,
    RfpSensorConfig,
    get_profile_registry,
)
from homeassistant.const import Platform
from tests.myrfplayer.rfprofiles.conftest import AnyTest, FrameExpectation, SensorTest


def _get_config(
    all_config: list[AnyRfpPlatformConfig], name: str
) -> AnyRfpPlatformConfig:
    named_config = next((v for v in all_config if v.name == name), None)
    # Check that named entity exists
    assert named_config
    return named_config


REGISTRY = get_profile_registry()


def _get_platform_tests(
    expectation: FrameExpectation, platform: Platform
) -> tuple[JsonPacketType, list[AnyRfpPlatformConfig], dict[str, AnyTest]]:
    event = expectation.given
    all_config = REGISTRY.get_platform_config(event, platform)

    assert all_config

    tests = expectation.then[platform]

    # same number of entities / platform
    assert len(all_config) == len(tests)

    return (event, all_config, tests)


def test_binary_sensor(profile: str, binary_sensor_expectation: FrameExpectation):
    """Test the binary sensors in the profile registry."""

    (event, all_config, tests) = _get_platform_tests(
        binary_sensor_expectation, Platform.BINARY_SENSOR
    )

    for name, test in tests.items():
        item = _get_config(all_config, name)

        assert isinstance(item, RfpSensorConfig)
        assert isinstance(test, SensorTest)
        assert item.config.get_value(event) == test.value, f"{name} value"


def test_sensor(profile: str, sensor_expectation: FrameExpectation):
    """Test the profile registry with an event."""

    (event, all_config, tests) = _get_platform_tests(
        sensor_expectation, Platform.SENSOR
    )

    for name, test in tests.items():
        item = _get_config(all_config, name)

        assert isinstance(item, RfpSensorConfig)
        assert isinstance(test, SensorTest)
        assert item.config.get_value(event) == test.value, f"{name} value"
        if item.config.unit_path:
            assert item.config.get_unit(event) == test.unit, f"{name} event unit"
        else:
            assert item.unit == test.unit, f"{name} default unit"
