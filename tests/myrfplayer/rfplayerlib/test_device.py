from typing import cast
from unittest.mock import Mock

from custom_components.myrfplayer.rfplayerlib.device import RfDeviceEvent, RfDeviceEventAdapter, RfDeviceId
from tests.myrfplayer.constants import BLYSS_ADDRESS, BLYSS_OFF_EVENT_DATA, OREGON_ADDRESS, OREGON_EVENT_DATA


def test_raw_event_callback_oregon():
    mock_callback = Mock()
    adapter = RfDeviceEventAdapter(mock_callback)
    adapter.raw_event_callback(OREGON_EVENT_DATA)

    event = cast(RfDeviceEvent, mock_callback.call_args[0][0])
    assert event.device == RfDeviceId(protocol="OREGON", address=OREGON_ADDRESS, model="PCR800")
    assert event.data == OREGON_EVENT_DATA


def test_raw_event_callback_blyss():
    mock_callback = Mock()
    adapter = RfDeviceEventAdapter(mock_callback)
    adapter.raw_event_callback(BLYSS_OFF_EVENT_DATA)

    event = cast(RfDeviceEvent, mock_callback.call_args[0][0])
    assert event.device == RfDeviceId(protocol="BLYSS", address=BLYSS_ADDRESS, model="switch")
    assert event.data == BLYSS_OFF_EVENT_DATA


def test_area_unit():
    device = RfDeviceId(protocol="X2D", address="2095907073")
    assert device.group_code == "1"
    assert device.unit_code == "130994192"

    device = RfDeviceId(protocol="CHACON", address="146139014")
    assert device.group_code == "6"
    assert device.unit_code == "2283422"

    device = RfDeviceId(protocol="X10", address="123")
    assert device.group_code == "7"
    assert device.unit_code == "11"

    device = RfDeviceId(protocol="RTS", address="123")
    assert device.group_code == "7"
    assert device.unit_code == "11"

    device = RfDeviceId(protocol="VISIONIC", address="123")
    assert device.group_code is None
    assert device.unit_code is None
