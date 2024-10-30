"""Constants for MyRfPlayer integration."""

CONF_RECONNECT_INTERVAL = "reconnect_interval"

DEFAULT_RECONNECT_INTERVAL = 10
DEFAULT_RECEIVER_PROTOCOLS = ["*"]

CONF_DEVICE_SIMULATOR = "device_simulator"
CONF_AUTOMATIC_ADD = "automatic_add"
CONF_RECEIVER_PROTOCOLS = "receiver_protocols"
CONF_INIT_COMMANDS = "init_commands"
CONF_ADD_DEVICE = "add_device"
CONF_REDIRECT_ADDRESS = "redirect_address"
ATTR_EVENT_DATA = "event_data"
ATTR_COMMAND = "command"
ATTR_INFO_TYPE = "info_type"
ATTR_INFOS = "infos"
CONNECTION_TIMEOUT = 10

SERVICE_SEND_RAW_COMMAND = "send_raw_command"
SERVICE_SIMULATE_EVENT = "simulate_event"

RFPLAYER_CLIENT = "rfplayer_client"
RFPLAYER_GATEWAY = "rfplayer_gateway"

DOMAIN = "myrfplayer"
SIGNAL_RFPLAYER_EVENT = f"{DOMAIN}_event"
SIGNAL_RFPLAYER_AVAILABILITY = f"{DOMAIN}_availability"

COMMAND_ON_LIST = ["true", "1", "on", "all_on"]
COMMAND_OFF_LIST = ["false", "0", "off", "all_on"]
COMMAND_GROUP_LIST = ["all_on", "all_off"]
