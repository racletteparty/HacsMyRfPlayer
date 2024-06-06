"""Constants for MyRfPlayer integration."""

CONF_RECONNECT_INTERVAL = "reconnect_interval"

DEFAULT_RECONNECT_INTERVAL = 10

CONF_MANUAL_DEVICE = "manual_device"
CONF_REPLACE_DEVICE = "replace_device"
CONF_AUTOMATIC_ADD = "automatic_add"
CONF_RECEIVER_PROTOCOLS = "receiver_protocols"
CONF_GROUP_ID = "group_id"
ATTR_EVENT_DATA = "event_data"
ATTR_COMMAND = "command"
ATTR_INFO_TYPE = "info_type"
ATTR_INFOS = "infos"
CONNECTION_TIMEOUT = 10

SERVICE_SEND = "send"

EVENT_RFPLAYER_EVENT = "rfp_event"

RFPLAYER_CLIENT = "rfp_client"

DOMAIN = "myrfplayer"
SIGNAL_RFPLAYER_EVENT = f"{DOMAIN}_event"
SIGNAL_RFPLAYER_AVAILABILITY = f"{DOMAIN}_availability"
