"""Support for RFXtrx binary sensors."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import logging
import math
from typing import cast

from custom_components.myrfplayer import RfDeviceEntity, async_setup_platform_entry
from custom_components.myrfplayer.rfplayerlib.device import RfDeviceId
from custom_components.myrfplayer.rfplayerlib.protocol import (
    JsonPacketType,
    RfPlayerRawEvent,
)
from custom_components.myrfplayer.rfprofiles.registry import (
    AnyRfpPlatformConfig,
    RfpPlatformConfig,
    RfpSensorConfig,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

_LOGGER = logging.getLogger(__name__)


def _get_entity_description(
    config: AnyRfpPlatformConfig,
) -> SensorEntityDescription:
    assert isinstance(config, RfpSensorConfig)
    return SensorEntityDescription(
        key=config.name,
        device_class=SensorDeviceClass(config.device_class)
        if config.device_class
        else None,
        native_unit_of_measurement=config.unit,
    )


def _builder(
    device: RfDeviceId,
    platform_config: list[AnyRfpPlatformConfig],
    event_data: RfPlayerRawEvent | None,
) -> list[Entity]:
    return [
        MyRfPlayerSensor(
            device,
            _get_entity_description(config),
            config,
            event_data=event_data,
        )
        for config in platform_config
    ]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up config rf device entry."""

    await async_setup_platform_entry(
        hass,
        config_entry,
        async_add_entities,
        Platform.SENSOR,
        _builder,
    )


class MyRfPlayerSensor(RfDeviceEntity, SensorEntity):
    """A representation of a RFXtrx binary sensor.

    Since all repeated events have meaning, these types of sensors
    need to have force update enabled.
    """

    _attr_force_update = True
    _attr_name = None

    def __init__(
        self,
        device: RfDeviceId,
        entity_description: SensorEntityDescription,
        platform_config: RfpPlatformConfig,
        event_data: RfPlayerRawEvent | None,
    ) -> None:
        """Initialize the RFXtrx sensor."""
        super().__init__(device)
        self.entity_description = entity_description
        assert isinstance(platform_config, RfpSensorConfig)
        self._config = cast(RfpSensorConfig, platform_config)
        self._event_data = event_data

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        """Return the state of the sensor."""
        if not self._event_data:
            return None
        assert isinstance(self._event_data, JsonPacketType)
        str_value = self._config.config.get_value(self._event_data)
        return float(str_value) if str_value else math.nan

    def _apply_event(self, event_data: RfPlayerRawEvent) -> None:
        """Apply command from RfPlayer."""
        super()._apply_event(event_data)

        _LOGGER.debug("Sensor update %s", self._device_id)
