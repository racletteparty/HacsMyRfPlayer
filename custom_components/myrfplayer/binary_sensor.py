"""Support for RFXtrx binary sensors."""

from __future__ import annotations

import logging
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
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)


def _get_entity_description(
    config: AnyRfpPlatformConfig,
) -> BinarySensorEntityDescription:
    return BinarySensorEntityDescription(
        key=config.name,
        device_class=BinarySensorDeviceClass(config.device_class)
        if config.device_class
        else None,
    )


def _builder(
    device: RfDeviceId,
    platform_config: list[AnyRfpPlatformConfig],
    event_data: RfPlayerRawEvent | None,
) -> list[Entity]:
    return [
        MyRfPlayerBinarySensor(
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
        Platform.BINARY_SENSOR,
        _builder,
    )


class MyRfPlayerBinarySensor(RfDeviceEntity, BinarySensorEntity):
    """A representation of a RfPlayer binary sensor."""

    _attr_force_update = True
    _attr_name = None

    def __init__(
        self,
        device: RfDeviceId,
        entity_description: BinarySensorEntityDescription,
        platform_config: RfpPlatformConfig,
        event_data: RfPlayerRawEvent | None,
    ) -> None:
        """Initialize the RfPlayer sensor."""
        super().__init__(device)
        self.entity_description = entity_description
        assert isinstance(platform_config, RfpSensorConfig)
        self._config = cast(RfpSensorConfig, platform_config)
        self._event_data = event_data
        # TODO add support for all_on / all_off group commands. extract group id from device id

    def _apply_event(self, event_data: RfPlayerRawEvent) -> None:
        """Apply command from RfPlayer."""
        super()._apply_event(event_data)

        _LOGGER.debug("Binary sensor update %s ", self._device_id)

        assert isinstance(event_data, JsonPacketType)
        self._attr_is_on = bool(self._config.config.get_value(event_data))
