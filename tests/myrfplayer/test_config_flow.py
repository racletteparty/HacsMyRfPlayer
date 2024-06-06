"""Test the RfPlayer config flow."""

import os
from typing import cast
from unittest.mock import MagicMock, Mock, patch, sentinel

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
import serial.tools.list_ports

from custom_components.myrfplayer import DOMAIN, config_flow
from custom_components.myrfplayer.const import RFPLAYER_CLIENT
from custom_components.myrfplayer.helpers import get_identifiers_from_device_id
from custom_components.myrfplayer.rfplayerlib import RfPlayerClient
from custom_components.myrfplayer.rfplayerlib.device import RfDeviceEvent, RfDeviceId
from custom_components.myrfplayer.rfplayerlib.protocol import RfPlayerEventData
from homeassistant import config_entries
from homeassistant.const import STATE_OFF, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from tests.myrfplayer.conftest import create_rfplayer_test_cfg
from tests.myrfplayer.constants import (
    OREGON_ADDRESS,
    OREGON_BINARY_SENSOR_ENTITY_ID,
    OREGON_BINARY_SENSOR_FRIENDLY_NAME,
    OREGON_DEVICE_INFO,
    OREGON_EVENT_DATA,
    OREGON_ID_STRING,
    OREGON_REDIRECT_ADDRESS,
)

SOME_PROTOCOLS = ["ac", "arc"]


def com_port():
    """Mock of a serial port."""
    port = serial.tools.list_ports_common.ListPortInfo("/dev/ttyUSB1234")
    port.serial_number = "1234"
    port.manufacturer = "Virtual serial port"
    port.device = "/dev/ttyUSB1234"
    port.description = "Some serial port"

    return port


async def start_options_flow(hass: HomeAssistant, entry: MockConfigEntry):
    """Start the options flow with the entry under test."""
    entry.add_to_hass(hass)

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    return await hass.config_entries.options.async_init(entry.entry_id)


@pytest.mark.asyncio
@patch("serial.tools.list_ports.comports", return_value=[com_port()])
async def test_setup_serial(serial_connection_mock: Mock, hass: HomeAssistant) -> None:
    """Test we can setup serial."""
    port = com_port()

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    with patch("custom_components.myrfplayer.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                "device": port.device,
            },
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "/dev/ttyUSB1234"
    assert result["data"] == {
        "device": port.device,
        "automatic_add": True,
        "reconnect_interval": 10,
        "receiver_protocols": ["*"],
        "init_commands": None,
        "devices": {},
        "redirect_address": {},
    }


@pytest.mark.asyncio
async def test_setup_serial_simulator(serial_connection_mock: Mock, hass: HomeAssistant) -> None:
    """Test we can setup serial with manual entry."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}

    with patch("custom_components.myrfplayer.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"device_simulator": True})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "/simulator"
    assert result["data"] == {
        "device": "/simulator",
        "automatic_add": True,
        "reconnect_interval": 10,
        "receiver_protocols": ["*"],
        "init_commands": None,
        "devices": {},
        "redirect_address": {},
    }


@pytest.mark.asyncio
async def test_options_global(serial_connection_mock: Mock, hass: HomeAssistant) -> None:
    """Test if we can set global options."""

    entry = MockConfigEntry(
        domain=DOMAIN,
        data=create_rfplayer_test_cfg(),
        unique_id=DOMAIN,
    )
    result = await start_options_flow(hass, entry)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "gateway_options"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"automatic_add": True, "reconnect_interval": 20, "receiver_protocols": ["RTS"]},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY

    await hass.async_block_till_done()

    assert entry.data["automatic_add"]
    assert entry.data["reconnect_interval"] == 20
    assert entry.data["receiver_protocols"] == ["RTS"]


@pytest.mark.asyncio
async def test_no_receiver_protocols(serial_connection_mock: Mock, hass: HomeAssistant) -> None:
    """Test we set protocols to None if none are selected."""

    entry = MockConfigEntry(
        domain=DOMAIN,
        data=create_rfplayer_test_cfg(),
        unique_id=DOMAIN,
    )
    result = await start_options_flow(hass, entry)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "gateway_options"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"automatic_add": False, "receiver_protocols": []},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY

    await hass.async_block_till_done()

    assert not entry.data["automatic_add"]

    assert entry.data["receiver_protocols"] is None


@pytest.mark.asyncio
async def test_init_commands(serial_connection_mock: Mock, hass: HomeAssistant) -> None:
    """Test we set protocols to None if none are selected."""

    entry = MockConfigEntry(
        domain=DOMAIN,
        data=create_rfplayer_test_cfg(),
        unique_id=DOMAIN,
    )
    result = await start_options_flow(hass, entry)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "gateway_options"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"automatic_add": False, "init_commands": "PING\nHELLO"},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY

    await hass.async_block_till_done()

    assert entry.data["init_commands"] == "PING\nHELLO"


@pytest.mark.asyncio
async def test_options_add_device(serial_connection_mock: Mock, hass: HomeAssistant) -> None:
    """Test we can add a device."""

    entry = MockConfigEntry(
        domain=DOMAIN,
        data=create_rfplayer_test_cfg(),
        unique_id=DOMAIN,
    )
    result = await start_options_flow(hass, entry)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "gateway_options"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"automatic_add": True, "add_device": True},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "add_rf_device"

    device_options = OREGON_DEVICE_INFO.copy()
    device_options.update({"profile_name": OREGON_DEVICE_INFO["profile_name"]})
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=device_options,
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY

    await hass.async_block_till_done()

    assert entry.data["automatic_add"]

    device_options = entry.data["devices"][OREGON_ID_STRING]

    assert not device_options["redirect_address"]
    assert device_options["profile_name"] == OREGON_DEVICE_INFO["profile_name"]

    state = hass.states.get(OREGON_BINARY_SENSOR_ENTITY_ID)
    assert state
    assert state.state == STATE_UNKNOWN
    assert state.attributes.get("friendly_name") == OREGON_BINARY_SENSOR_FRIENDLY_NAME


@pytest.mark.asyncio
async def test_options_configure_device(
    serial_connection_mock: Mock, hass: HomeAssistant, device_registry: dr.DeviceRegistry
) -> None:
    """Test we can add a device."""

    entry = MockConfigEntry(
        domain=DOMAIN,
        data=create_rfplayer_test_cfg(devices={OREGON_ID_STRING: OREGON_DEVICE_INFO}),
        unique_id=DOMAIN,
    )
    result = await start_options_flow(hass, entry)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "gateway_options"

    device_id = RfDeviceId(protocol="OREGON", address=OREGON_ADDRESS)
    device_entry = device_registry.async_get_device(identifiers=get_identifiers_from_device_id(device_id))
    assert device_entry

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "device": device_entry.id,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "rf_device_options"

    # ----------------------------------------------------------------------------------

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"redirect_address": OREGON_REDIRECT_ADDRESS},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY

    await hass.async_block_till_done()

    assert entry.data["automatic_add"]

    assert entry.data["devices"][OREGON_ID_STRING]["redirect_address"] == OREGON_REDIRECT_ADDRESS
    assert entry.data["devices"][OREGON_ID_STRING]["profile_name"] == OREGON_DEVICE_INFO["profile_name"]

    state = hass.states.get(OREGON_BINARY_SENSOR_ENTITY_ID)
    assert state
    assert state.state == STATE_UNKNOWN
    assert state.attributes.get("friendly_name") == OREGON_BINARY_SENSOR_FRIENDLY_NAME

    client = cast(RfPlayerClient, hass.data[DOMAIN][RFPLAYER_CLIENT])

    client.event_callback(
        RfDeviceEvent(
            device=RfDeviceId(protocol="OREGON", address=OREGON_REDIRECT_ADDRESS, model="PCR800"),
            data=RfPlayerEventData(OREGON_EVENT_DATA),
        )
    )

    state = hass.states.get(OREGON_BINARY_SENSOR_ENTITY_ID)
    assert state
    assert state.state == STATE_OFF

    # ----------------------------------------------------------------------------------

    device_entries = dr.async_entries_for_config_entry(device_registry, entry.entry_id)

    assert device_entries[0].id

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "gateway_options"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "automatic_add": False,
            "device": device_entries[0].id,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "rf_device_options"

    # ----------------------------------------------------------------------------------

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY

    await hass.async_block_till_done()

    assert not entry.data["devices"][OREGON_ID_STRING]["redirect_address"]
    assert entry.data["devices"][OREGON_ID_STRING]["profile_name"] == OREGON_DEVICE_INFO["profile_name"]


def test_get_serial_by_id_no_dir() -> None:
    """Test serial by id conversion if there's no /dev/serial/by-id."""
    p1 = patch("os.path.isdir", MagicMock(return_value=False))
    p2 = patch("os.scandir")
    with p1 as is_dir_mock, p2 as scan_mock:
        res = config_flow.get_serial_by_id(sentinel.path)
        assert res is sentinel.path
        assert is_dir_mock.call_count == 1
        assert scan_mock.call_count == 0


def test_get_serial_by_id() -> None:
    """Test serial by id conversion."""
    p1 = patch("os.path.isdir", MagicMock(return_value=True))
    p2 = patch("os.scandir")

    def _realpath(path):
        if path is sentinel.matched_link:
            return sentinel.path
        return sentinel.serial_link_path

    p3 = patch("os.path.realpath", side_effect=_realpath)
    with p1 as is_dir_mock, p2 as scan_mock, p3:
        res = config_flow.get_serial_by_id(sentinel.path)
        assert res is sentinel.path
        assert is_dir_mock.call_count == 1
        assert scan_mock.call_count == 1

        entry1 = MagicMock(spec_set=os.DirEntry)
        entry1.is_symlink.return_value = True
        entry1.path = sentinel.some_path

        entry2 = MagicMock(spec_set=os.DirEntry)
        entry2.is_symlink.return_value = False
        entry2.path = sentinel.other_path

        entry3 = MagicMock(spec_set=os.DirEntry)
        entry3.is_symlink.return_value = True
        entry3.path = sentinel.matched_link

        scan_mock.return_value = [entry1, entry2, entry3]
        res = config_flow.get_serial_by_id(sentinel.path)
        assert res is sentinel.matched_link
        assert is_dir_mock.call_count == 2
        assert scan_mock.call_count == 2
