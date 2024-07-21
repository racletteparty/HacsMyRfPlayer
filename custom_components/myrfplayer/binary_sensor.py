"""Support for RFXtrx binary sensors."""

from __future__ import annotations

import logging
from typing import cast

from custom_components.myrfplayer import RfDeviceEntity, async_setup_platform_entry
from custom_components.myrfplayer.rfplayerlib.device import RfDeviceEvent, RfDeviceId
from custom_components.myrfplayer.rfplayerlib.protocol import JsonPacketType
from custom_components.myrfplayer.rfprofiles.registry import (
    PlatformConfig,
    SensorProfileConfig,
)
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

_LOGGER = logging.getLogger(__name__)


def _get_entity_description(
    key: str, config: PlatformConfig
) -> BinarySensorEntityDescription:
    return BinarySensorEntityDescription(
        key=key, device_class=BinarySensorDeviceClass(config.device_class)
    )


def _builder(
    device: RfDeviceId,
    platform_config: dict[str, PlatformConfig],
    event: RfDeviceEvent | None,
) -> list[Entity]:
    return [
        MyRfPlayerBinarySensor(
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
        rfplayer_config: PlatformConfig,
        event: RfDeviceEvent | None,
    ) -> None:
        """Initialize the RfPlayer sensor."""
        super().__init__(device)
        self.entity_description = entity_description
        assert isinstance(rfplayer_config, SensorProfileConfig)
        self._rfplayer_config = cast(SensorProfileConfig, rfplayer_config)
        self._event = event

    def _apply_event(self, event: RfDeviceEvent) -> None:
        """Apply command from RfPlayer."""
        super()._apply_event(event)
        assert isinstance(event.data, JsonPacketType)
        self._attr_is_on = bool(self._rfplayer_config.sensor.get_value(event.data))

    @callback
    def _handle_event(self, event: RfDeviceEvent) -> None:
        """Check if event applies to me and update."""
        if not self._event_applies(event):
            return

        _LOGGER.debug(
            "Binary sensor update %s (Proto: %s Addr: %s Model: %s)",
            event.device.device_id,
            event.device.protocol,
            event.device.address,
            event.device.model,
        )

        self._apply_event(event)

        self.async_write_ha_state()
