"""RfPlayer Oregon device profiles."""

from dataclasses import dataclass

from custom_components.myrfplayer.rfprofiles.registry import (
    DeviceProfile,
    JsonValueConfig,
    PlatformConfig,
    SensorProfileConfig,
)
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS,
    Platform,
    UnitOfTemperature,
)


@dataclass
class OregonTempDevice(DeviceProfile):
    """Oregon temperature sensor."""

    platforms: dict[Platform, dict[str, PlatformConfig]] = {
        Platform.SENSOR: {
            "Low battery": SensorProfileConfig(
                device_class=BinarySensorDeviceClass.BATTERY,
                unit=PERCENTAGE,
                sensor=JsonValueConfig(
                    info_type="4",
                    json_path="$.frame.infos.lowBatt",
                    bit_mask=1,
                    factor=100.0,
                ),
            ),
            "Temperature": SensorProfileConfig(
                device_class=SensorDeviceClass.TEMPERATURE,
                sensor=JsonValueConfig(
                    info_type="4",
                    json_path="$.frame.infos.measures[?(@.type=='temperature')].value",
                ),
            ),
            "Rf Level": SensorProfileConfig(
                device_class=SensorDeviceClass.SIGNAL_STRENGTH,
                unit=SIGNAL_STRENGTH_DECIBELS,
                sensor=JsonValueConfig(info_type="4", json_path="$.frame.rfLevel"),
            ),
        },
    }


@dataclass
class OregonTempHygroDevice(DeviceProfile):
    """Oregon temperature sensor."""

    platforms: dict[Platform, dict[str, PlatformConfig]] = {
        Platform.SENSOR: {
            "Low battery": SensorProfileConfig(
                device_class=BinarySensorDeviceClass.BATTERY,
                unit=PERCENTAGE,
                sensor=JsonValueConfig(
                    info_type="4",
                    json_path="$.frame.infos.lowBatt",
                    bit_mask=1,
                    factor=100.0,
                ),
            ),
            "Temperature": SensorProfileConfig(
                device_class=SensorDeviceClass.TEMPERATURE,
                unit=UnitOfTemperature.CELSIUS,
                sensor=JsonValueConfig(
                    info_type="4",
                    json_path="$.frame.infos.measures[?(@.type=='temperature')].value",
                ),
            ),
            "Humidity": SensorProfileConfig(
                device_class=SensorDeviceClass.HUMIDITY,
                unit=PERCENTAGE,
                sensor=JsonValueConfig(
                    info_type="4",
                    json_path="$.frame.infos.measures[?(@.type=='humidity')].value",
                ),
            ),
            "Rf Level": SensorProfileConfig(
                device_class=SensorDeviceClass.SIGNAL_STRENGTH,
                unit=SIGNAL_STRENGTH_DECIBELS,
                sensor=JsonValueConfig(info_type="4", json_path="$.frame.rfLevel"),
            ),
        },
    }


@dataclass
class OregonPressureDevice(DeviceProfile):
    """Oregon temperature sensor."""

    platforms: dict[Platform, dict[str, PlatformConfig]] = {
        Platform.SENSOR: {
            "Low battery": SensorProfileConfig(
                device_class=BinarySensorDeviceClass.BATTERY,
                unit=PERCENTAGE,
                sensor=JsonValueConfig(
                    info_type="5",
                    json_path="$.frame.infos.lowBatt",
                    bit_mask=1,
                    factor=100.0,
                ),
            ),
            "Temperature": SensorProfileConfig(
                device_class=SensorDeviceClass.TEMPERATURE,
                sensor=JsonValueConfig(
                    info_type="5",
                    json_path="$.frame.infos.measures[?(@.type=='temperature')].value",
                ),
            ),
            "Humidity": SensorProfileConfig(
                device_class=SensorDeviceClass.HUMIDITY,
                sensor=JsonValueConfig(
                    info_type="5",
                    json_path="$.frame.infos.measures[?(@.type=='humidity')].value",
                ),
            ),
            "Pressure": SensorProfileConfig(
                device_class=SensorDeviceClass.PRESSURE,
                sensor=JsonValueConfig(
                    info_type="5",
                    json_path="$.frame.infos.measures[?(@.type=='pressure')].value",
                ),
            ),
            "Rf Level": SensorProfileConfig(
                device_class=SensorDeviceClass.SIGNAL_STRENGTH,
                sensor=JsonValueConfig(info_type="5", json_path="$.frame.rfLevel"),
            ),
        },
    }
