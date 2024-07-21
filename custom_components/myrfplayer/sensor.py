"""Support for RFXtrx binary sensors."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import logging
import math
from typing import cast

from custom_components.myrfplayer import RfDeviceEntity, async_setup_platform_entry
from custom_components.myrfplayer.rfplayerlib.device import RfDeviceEvent, RfDeviceId
from custom_components.myrfplayer.rfplayerlib.protocol import JsonPacketType
from custom_components.myrfplayer.rfprofiles.registry import (
    PlatformConfig,
    SensorProfileConfig,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

_LOGGER = logging.getLogger(__name__)


def _get_entity_description(
    key: str, config: PlatformConfig
) -> SensorEntityDescription:
    assert isinstance(config, SensorProfileConfig)
    return SensorEntityDescription(
        key=key,
        device_class=SensorDeviceClass(config.device_class),
        native_unit_of_measurement=config.unit,
    )


def _builder(
    device: RfDeviceId,
    platform_config: dict[str, PlatformConfig],
    event: RfDeviceEvent | None,
) -> list[Entity]:
    return [
        MyRfPlayerSensor(
            device,
            _get_entity_description(key, config),
            config,
            event=event,
        )
        for key, config in platform_config.items()
    ]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up config rf device entry."""

    await async_setup_platform_entry(
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
        rfplayer_config: PlatformConfig,
        event: RfDeviceEvent | None,
    ) -> None:
        """Initialize the RFXtrx sensor."""
        super().__init__(device)
        self.entity_description = entity_description
        assert isinstance(rfplayer_config, SensorProfileConfig)
        self._rfplayer_config = cast(SensorProfileConfig, rfplayer_config)
        self._event = event

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        """Return the state of the sensor."""
        if not self._event:
            return None
        assert isinstance(self._event.data, JsonPacketType)
        str_value = self._rfplayer_config.sensor.get_value(self._event.data)
        return float(str_value) if str_value else math.nan

    @callback
    def _handle_event(self, event: RfDeviceEvent) -> None:
        """Check if event applies to me and update."""
        if not self._event_applies(event):
            return

        _LOGGER.debug(
            "Sensor update %s (Proto: %s Addr: %s Model: %s)",
            event.device.device_id,
            event.device.protocol,
            event.device.address,
            event.device.model,
        )

        self._apply_event(event)

        self.async_write_ha_state()
