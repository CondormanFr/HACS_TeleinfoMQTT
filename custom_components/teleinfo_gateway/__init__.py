
from __future__ import annotations
import asyncio, logging, contextlib, json
from typing import Dict, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    DOMAIN, PLATFORMS,
    DEFAULT_DECODE, DEFAULT_TIMEOUT,
    EVT_RAW, EVT_FRAME,
    OPT_MQTT_ENABLE, OPT_MQTT_TOPIC_LINE, OPT_MQTT_TOPIC_JSON, OPT_MQTT_TOPIC_FIELDS,
    OPT_MQTT_TOPIC_INVALID, OPT_MQTT_TOPIC_DERIVED, OPT_HA_DISCOVERY, OPT_HA_DISCOVERY_PREFIX,
    OPT_HA_DEVICE_NAME, OPT_INCLUDE_WH,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    conf = entry.data
    opts = entry.options

    port = conf.get("port")
    baud = conf.get("baud")
    bytesize = conf.get("bytesize")
    parity = conf.get("parity")
    stopbits = conf.get("stopbits")
    timeout = conf.get("timeout", DEFAULT_TIMEOUT)
    decode = conf.get("decode", DEFAULT_DECODE)
    relaxed = set(conf.get("relaxed_labels", []))

    # MQTT mirror & discovery options
    mqtt_enable = opts.get(OPT_MQTT_ENABLE, True)
    ha_disc = opts.get(OPT_HA_DISCOVERY, True)
    disc_prefix = opts.get(OPT_HA_DISCOVERY_PREFIX, "homeassistant")
    device_name = opts.get(OPT_HA_DEVICE_NAME, "")
    include_wh = opts.get(OPT_INCLUDE_WH, False)

    topic_line = opts.get(OPT_MQTT_TOPIC_LINE, "teleinfo/line")
    topic_json = opts.get(OPT_MQTT_TOPIC_JSON, "teleinfo/json")
    topic_fields = opts.get(OPT_MQTT_TOPIC_FIELDS, "teleinfo/fields")
    topic_invalid = opts.get(OPT_MQTT_TOPIC_INVALID, "teleinfo/invalid")
    topic_derived = opts.get(OPT_MQTT_TOPIC_DERIVED, "teleinfo/derived")

    # Import here to avoid blocking HA startup if pyserial not installed yet
    import serial_asyncio
    from serial import EIGHTBITS, SEVENBITS, PARITY_NONE, PARITY_EVEN, STOPBITS_ONE, STOPBITS_TWO

    bits = EIGHTBITS if bytesize == 8 else SEVENBITS
    par = PARITY_NONE if str(parity).upper() == "N" else PARITY_EVEN
    stop = STOPBITS_ONE if stopbits == 1 else STOPBITS_TWO

    session = TeleinfoSession(
        hass=hass,
        port=port, baud=baud, bits=bits, parity=par, stopbits=stop,
        timeout=timeout, decode=decode, relaxed_labels=relaxed,
        mqtt_enable=mqtt_enable,
        topic_line=topic_line,
        topic_json=topic_json,
        topic_fields=topic_fields,
        topic_invalid=topic_invalid,
        topic_derived=topic_derived,
        ha_discovery=ha_disc,
        ha_discovery_prefix=disc_prefix,
        ha_device_name=device_name,
        include_wh=include_wh,
    )

    try:
        await session.start()
    except Exception as e:
        raise ConfigEntryNotReady(f"Serial open failed on {port}: {e}")

    hass.data[DOMAIN][entry.entry_id] = session

    await hass.config_entries.async_forward_entry_setups(entry, [Platform.SENSOR])

    # Clean stop
    entry.async_on_unload(session.stop)

    # Reload sensors when options change
    entry.async_on_unload(entry.add_update_listener(_reload_on_update))

    return True

async def _reload_on_update(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, [Platform.SENSOR]):
        session: TeleinfoSession = hass.data[DOMAIN].pop(entry.entry_id)
        await session.async_close()
    return unload_ok

# -----------------------------
# Teleinfo engine
# -----------------------------
STX = 0x02
ETX = 0x03
LF  = 0x0A

class TeleinfoSession:
    def __init__(self, hass: HomeAssistant, *, port: str, baud: int, bits, parity, stopbits,
                 timeout: float, decode: str, relaxed_labels: set,
                 mqtt_enable: bool, topic_line: str, topic_json: str, topic_fields: str, topic_invalid: str, topic_derived: str,
                 ha_discovery: bool, ha_discovery_prefix: str, ha_device_name: str, include_wh: bool):
        self.hass = hass
        self.port = port
        self.baud = baud
        self.bits = bits
        self.parity = parity
        self.stopbits = stopbits
        self.timeout = timeout
        self.decode = decode
        self.relaxed_labels = relaxed_labels
        self.transport = None
        self.protocol = None
        self._task = None
        self._ha_discovery_done = False
        self.mqtt_enable = mqtt_enable
        self.topic_line = topic_line
        self.topic_json = topic_json
        self.topic_fields = topic_fields
        self.topic_invalid = topic_invalid
        self.topic_derived = topic_derived
        self.ha_discovery = ha_discovery
        self.ha_discovery_prefix = ha_discovery_prefix
        self.ha_device_name = ha_device_name
        self.include_wh = include_wh

    async def start(self):
        import serial_asyncio
        loop = asyncio.get_running_loop()
        self.transport, self.protocol = await serial_asyncio.create_serial_connection(
            loop, lambda: _TeleinfoProto(self), self.port, baudrate=self.baud,
            bytesize=self.bits, parity=self.parity, stopbits=self.stopbits,
            timeout=self.timeout
        )

    async def async_close(self):
        if self.transport:
            self.transport.close()
        if self._task:
            self._task.cancel()
            with contextlib.suppress(Exception):
                await self._task

    def stop(self):
        asyncio.create_task(self.async_close())

    # ------------- helpers -------------
    @staticmethod
    def _tic_checksum_ok(label: str, value: str, chk_char: str) -> bool:
        total = 0
        for ch in (label + " " + value):
            total += ord(ch)
        calc = (total & 0x3F) + 0x20
        return len(chk_char) == 1 and ord(chk_char) == calc

    def parse_tic_line(self, s: str):
        raw = s
        s = s.strip("\r\n")
        if not s:
            return (None, None, None, False)
        parts = s.split()
        if len(parts) < 2:
            return (None, None, None, False)
        label = parts[0]
        if len(parts) >= 3:
            value = " ".join(parts[1:-1])
            chk = parts[-1]
            ok = False
            if len(chk) == 1:
                ok = self._tic_checksum_ok(label, value, chk)
                if not ok and label in self.relaxed_labels:
                    v2 = value.replace("\t", "")
                    ok = self._tic_checksum_ok(label, v2, chk)
                    if ok:
                        value = v2
                    if not ok:
                        v3 = " ".join(value.split())
                        ok = self._tic_checksum_ok(label, v3, chk)
                        if ok:
                            value = v3
            if ok:
                return (label, value, chk, True)
            else:
                return (label, " ".join(parts[1:]), chk if len(chk) == 1 else "", False)
        else:
            return (label, parts[1], "", False)

    @staticmethod
    def ptec_friendly(code: str):
        c = (code or "").strip().upper()
        tempo = {
            "HCJB": ("Heures Creuses (Tempo Bleu)",  "HC_BLEU",  "mdi:weather-night"),
            "HPJB": ("Heures Pleines (Tempo Bleu)", "HP_BLEU",  "mdi:white-balance-sunny"),
            "HCJW": ("Heures Creuses (Tempo Blanc)","HC_BLANC", "mdi:weather-night"),
            "HPJW": ("Heures Pleines (Tempo Blanc)","HP_BLANC", "mdi:white-balance-sunny"),
            "HCJR": ("Heures Creuses (Tempo Rouge)","HC_ROUGE", "mdi:weather-night"),
            "HPJR": ("Heures Pleines (Tempo Rouge)","HP_ROUGE", "mdi:white-balance-sunny"),
        }
        if c in tempo: return tempo[c]
        if c.startswith("HC"): return ("Heures Creuses", "HC", "mdi:weather-night")
        if c.startswith("HP"): return ("Heures Pleines", "HP", "mdi:white-balance-sunny")
        if c.startswith("TH"): return ("Toutes Heures", "TH", "mdi:clock-outline")
        if c.startswith("HN"): return ("Heures Normales", "HN", "mdi:timer-outline")
        if c.startswith("PM"): return ("Pointe Mobile", "PM", "mdi:flash-alert")
        return ("Inconnu", "UNK", "mdi:clock-alert")

    async def publish_mqtt(self, topic: str, payload: str, retain: bool=False):
        mqtt = self.hass.components.mqtt
        await mqtt.async_publish(topic, payload, qos=0, retain=retain)

    async def publish_discovery(self, adco: str, present: set):
        dev = {
            "identifiers": [f"teleinfo_{adco}"],
            "name": self.ha_device_name or f"Téléinfo {adco}",
            "manufacturer": "Enedis",
            "model": "Linky (TIC historique)",
        }
        def sensor_cfg(uid: str, name: str, state_topic: str, **kw):
            cfg = {
                "name": name,
                "unique_id": uid,
                "state_topic": state_topic,
                "availability_topic": f"{self.topic_derived}/ha_avail",
                "payload_available": "online",
                "payload_not_available": "offline",
                "device": dev,
            }
            cfg.update({k: v for k, v in kw.items() if v is not None})
            return cfg

        async def pub_cfg(ptype: str, uid: str, cfg: dict):
            await self.publish_mqtt(f"{self.ha_discovery_prefix}/{ptype}/{uid}/config", json.dumps(cfg, ensure_ascii=False), retain=True)

        # PAPP
        if "PAPP" in present:
            await pub_cfg("sensor", f"teleinfo_{adco}_papp", sensor_cfg(
                f"teleinfo_{adco}_papp", "Téléinfo PAPP", f"{self.topic_fields}/PAPP",
                unit_of_measurement="VA", state_class="measurement", icon="mdi:flash"
            ))
        # IINST
        if "IINST" in present:
            await pub_cfg("sensor", f"teleinfo_{adco}_iinst", sensor_cfg(
                f"teleinfo_{adco}_iinst", "Téléinfo IINST", f"{self.topic_fields}/IINST",
                unit_of_measurement="A", device_class="current", state_class="measurement", icon="mdi:current-ac"
            ))
        # IMAX
        if "IMAX" in present:
            await pub_cfg("sensor", f"teleinfo_{adco}_imax", sensor_cfg(
                f"teleinfo_{adco}_imax", "Téléinfo IMAX", f"{self.topic_fields}/IMAX",
                unit_of_measurement="A", device_class="current", state_class="measurement", icon="mdi:current-ac"
            ))
        # Index énergie (Wh->kWh) + option Wh
        for lbl, nice in [("BASE", "INDEX BASE"), ("HCHC", "INDEX HCHC"), ("HCHP", "INDEX HCHP")]:
            if lbl in present:
                await pub_cfg("sensor", f"teleinfo_{adco}_{lbl.lower()}_kwh", sensor_cfg(
                    f"teleinfo_{adco}_{lbl.lower()}_kwh", f"Téléinfo {nice} (kWh)", f"{self.topic_fields}/{lbl}",
                    unit_of_measurement="kWh", device_class="energy", state_class="total_increasing",
                    value_template="{{ (value | float(0)) / 1000 }}", icon="mdi:counter"
                ))
                if self.include_wh:
                    await pub_cfg("sensor", f"teleinfo_{adco}_{lbl.lower()}_wh", sensor_cfg(
                        f"teleinfo_{adco}_{lbl.lower()}_wh", f"Téléinfo {nice} (Wh)", f"{self.topic_fields}/{lbl}",
                        unit_of_measurement="Wh", device_class="energy", state_class="total_increasing",
                        icon="mdi:counter"
                    ))
        # PTEC brut + friendly + HC actif (binary)
        if "PTEC" in present:
            await pub_cfg("sensor", f"teleinfo_{adco}_ptec", sensor_cfg(
                f"teleinfo_{adco}_ptec", "Téléinfo PTEC", f"{self.topic_fields}/PTEC", icon="mdi:clock-outline"
            ))
            await pub_cfg("sensor", f"teleinfo_{adco}_tarif", sensor_cfg(
                f"teleinfo_{adco}_tarif", "Téléinfo Tarif courant", f"{self.topic_derived}/ptec_friendly", icon="mdi:clock-time-four-outline"
            ))
            await pub_cfg("binary_sensor", f"teleinfo_{adco}_hc_active", sensor_cfg(
                f"teleinfo_{adco}_hc_active", "Téléinfo Heures Creuses", f"{self.topic_derived}/hc_active", icon="mdi:weather-night"
            ))

        # Mark HA availability for discovery entities
        await self.publish_mqtt(f"{self.topic_derived}/ha_avail", "online", retain=True)

class _TeleinfoProto(asyncio.Protocol):
    def __init__(self, session: TeleinfoSession):
        self.sess = session
        self.buf = bytearray()
        self.in_frame = False
        self.frame_lines = []
        self.stats_invalid = 0

    def data_received(self, data: bytes):
        for b in data:
            if b == 0x02:  # STX
                self.in_frame = True
                self.frame_lines.clear()
                self.buf.clear()
                continue
            if b == 0x03:  # ETX
                frame_obj: Dict[str, Any] = {"_meta": {"invalid_lines": self.stats_invalid}}
                self.stats_invalid = 0
                present = set()
                for raw in self.frame_lines:
                    try:
                        label, value, chk, ok = self.sess.parse_tic_line(raw)
                        if label and value is not None:
                            frame_obj[label] = value
                            present.add(label)
                            # Push per-field
                            if self.sess.mqtt_enable:
                                asyncio.create_task(self.sess.publish_mqtt(f"{self.sess.topic_fields}/{label}", str(value)))
                            if not ok and self.sess.mqtt_enable:
                                inv = {
                                    "label": label,
                                    "raw": raw.strip("\r\n"),
                                    "hex": " ".join(f"{ord(c):02X}" for c in raw),
                                }
                                asyncio.create_task(self.sess.publish_mqtt(self.sess.topic_invalid, json.dumps(inv, ensure_ascii=False)))
                    except Exception:
                        pass
                # Derived
                ptec_code = frame_obj.get("PTEC", "")
                friendly, short, _icon = self.sess.ptec_friendly(ptec_code)
                if self.sess.mqtt_enable:
                    asyncio.create_task(self.sess.publish_mqtt(f"{self.sess.topic_derived}/ptec_friendly", friendly))
                    asyncio.create_task(self.sess.publish_mqtt(f"{self.sess.topic_derived}/ptec_short", short))
                    asyncio.create_task(self.sess.publish_mqtt(f"{self.sess.topic_derived}/hc_active", "ON" if short.startswith("HC") else "OFF"))

                # One-shot MQTT discovery once ADCO known
                if self.sess.ha_discovery and not self.sess._ha_discovery_done:
                    adco = frame_obj.get("ADCO")
                    if adco:
                        asyncio.create_task(self.sess.publish_discovery(adco, present))
                        self.sess._ha_discovery_done = True

                # Whole frame
                if self.sess.mqtt_enable:
                    asyncio.create_task(self.sess.publish_mqtt(self.sess.topic_json, json.dumps(frame_obj, ensure_ascii=False)))

                # Notify HA listeners (entities)
                self.sess.hass.bus.async_fire(EVT_FRAME, {"frame": frame_obj})

                self.in_frame = False
                self.frame_lines.clear()
                self.buf.clear()
                continue

            if b == 0x0A:  # LF
                try:
                    line = self.buf.decode(self.sess.decode, errors="ignore")
                except Exception:
                    line = ""
                if line:
                    if self.sess.mqtt_enable:
                        asyncio.create_task(self.sess.publish_mqtt(self.sess.topic_line, line.strip("\r\n")))
                    if self.in_frame:
                        self.frame_lines.append(line)
                else:
                    self.stats_invalid += 1
                self.buf.clear()
            else:
                self.buf.append(b)
