import json
import os
from pathlib import Path

from pydantic import BaseModel, parse_obj_as

from homeassistant.const import Platform

from custom_components.myrfplayer.rfplayerlib.protocol import JsonPacketType

FRAMES_PATH = Path(os.path.abspath(__file__)).parent / "frames"


class SensorTest(BaseModel):
    value: str
    unit: str | None


AnyTest = SensorTest


class FrameExpectation(BaseModel):
    given: JsonPacketType
    then: dict[Platform, dict[str, AnyTest]]


def _load_expectations(platform: Platform) -> list[tuple[str, FrameExpectation]]:
    result = []
    for filename in FRAMES_PATH.glob("*.json"):
        with open(filename, encoding="utf-8") as f:
            obj = json.load(f)
            expectations = parse_obj_as(list[FrameExpectation], obj)
            result.extend(
                [(filename.name, e) for e in expectations if platform in e.then]
            )
    return result


def pytest_generate_tests(metafunc):
    if "profile" in metafunc.fixturenames:
        if "binary_sensor_expectation" in metafunc.fixturenames:
            metafunc.parametrize(
                "profile,binary_sensor_expectation",
                _load_expectations(Platform.BINARY_SENSOR),
            )
        if "sensor_expectation" in metafunc.fixturenames:
            metafunc.parametrize(
                "profile,sensor_expectation", _load_expectations(Platform.SENSOR)
            )
