
from __future__ import annotations
from typing import Any
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN

async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    return {
        "port": entry.data.get("port"),
        "baud": entry.data.get("baud"),
        "relaxed_labels": entry.data.get("relaxed_labels"),
        "mqtt_mirror": entry.options.get("mqtt_enable", True),
        "topics": {
            "line": entry.options.get("mqtt_topic_line"),
            "json": entry.options.get("mqtt_topic_json"),
            "fields": entry.options.get("mqtt_topic_fields"),
            "invalid": entry.options.get("mqtt_topic_invalid"),
            "derived": entry.options.get("mqtt_topic_derived"),
        },
        "ha_discovery": entry.options.get("ha_discovery", True),
    }
