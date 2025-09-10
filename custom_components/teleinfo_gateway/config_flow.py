
from __future__ import annotations
from typing import Any
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    DOMAIN, DEFAULT_PORT, DEFAULT_BAUD, DEFAULT_BYTESIZE, DEFAULT_PARITY, DEFAULT_STOPBITS, DEFAULT_TIMEOUT, DEFAULT_DECODE, DEFAULT_RELAXED,
    OPT_MQTT_ENABLE, OPT_MQTT_TOPIC_LINE, OPT_MQTT_TOPIC_JSON, OPT_MQTT_TOPIC_FIELDS, OPT_MQTT_TOPIC_INVALID, OPT_MQTT_TOPIC_DERIVED,
    OPT_HA_DISCOVERY, OPT_HA_DISCOVERY_PREFIX, OPT_HA_DEVICE_NAME, OPT_INCLUDE_WH,
)

RELAX_CHOICES = [
    "PTEC", "ADCO", "BASE", "HCHC", "HCHP", "PAPP", "IINST", "IMAX", "ISOUSC"
]

SERIAL_SCHEMA = vol.Schema({
    vol.Required("port", default=DEFAULT_PORT): str,
    vol.Required("baud", default=DEFAULT_BAUD): vol.Coerce(int),
    vol.Required("bytesize", default=DEFAULT_BYTESIZE): vol.In([7,8]),
    vol.Required("parity", default=DEFAULT_PARITY): vol.In(["E", "N"]),
    vol.Required("stopbits", default=DEFAULT_STOPBITS): vol.In([1,2]),
    vol.Optional("timeout", default=DEFAULT_TIMEOUT): vol.Coerce(float),
    vol.Optional("decode", default=DEFAULT_DECODE): str,
    vol.Optional("relaxed_labels", default=DEFAULT_RELAXED): selector.SelectSelector(
        selector.SelectSelectorConfig(options=RELAX_CHOICES, multiple=True, mode="list")
    ),
})

OPTIONS_SCHEMA = vol.Schema({
    vol.Required(OPT_MQTT_ENABLE, default=True): bool,
    vol.Required(OPT_HA_DISCOVERY, default=True): bool,
    vol.Optional(OPT_HA_DISCOVERY_PREFIX, default="homeassistant"): str,
    vol.Optional(OPT_HA_DEVICE_NAME, default=""): str,
    vol.Required(OPT_INCLUDE_WH, default=False): bool,

    vol.Optional(OPT_MQTT_TOPIC_LINE, default="teleinfo/line"): str,
    vol.Optional(OPT_MQTT_TOPIC_JSON, default="teleinfo/json"): str,
    vol.Optional(OPT_MQTT_TOPIC_FIELDS, default="teleinfo/fields"): str,
    vol.Optional(OPT_MQTT_TOPIC_INVALID, default="teleinfo/invalid"): str,
    vol.Optional(OPT_MQTT_TOPIC_DERIVED, default="teleinfo/derived"): str,
})

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="Téléinfo Gateway", data=user_input)
        return self.async_show_form(step_id="user", data_schema=SERIAL_SCHEMA)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlowHandler(config_entry)

class OptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, entry):
        self.entry = entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="Options", data=user_input)
        return self.async_show_form(step_id="init", data_schema=OPTIONS_SCHEMA)
