
DOMAIN = "teleinfo_gateway"
PLATFORMS = ["sensor"]
DEFAULT_PORT = "/dev/ttyUSB0"
DEFAULT_BAUD = 1200
DEFAULT_BYTESIZE = 7
DEFAULT_PARITY = "E"
DEFAULT_STOPBITS = 1
DEFAULT_TIMEOUT = 1.0
DEFAULT_DECODE = "latin-1"
DEFAULT_RELAXED = ["PTEC"]

# MQTT mirror & discovery
OPT_MQTT_ENABLE = "mqtt_enable"
OPT_MQTT_TOPIC_LINE = "mqtt_topic_line"
OPT_MQTT_TOPIC_JSON = "mqtt_topic_json"
OPT_MQTT_TOPIC_FIELDS = "mqtt_topic_fields"
OPT_MQTT_TOPIC_INVALID = "mqtt_topic_invalid"
OPT_MQTT_TOPIC_DERIVED = "mqtt_topic_derived"
OPT_HA_DISCOVERY = "ha_discovery"
OPT_HA_DISCOVERY_PREFIX = "ha_discovery_prefix"
OPT_HA_DEVICE_NAME = "ha_device_name"
OPT_INCLUDE_WH = "include_wh"

# Derived keys
EVT_RAW = f"{DOMAIN}_raw"
EVT_FRAME = f"{DOMAIN}_frame"
