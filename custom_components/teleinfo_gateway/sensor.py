
from __future__ import annotations
from typing import Any, Dict, List
from datetime import datetime
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.const import UnitOfElectricCurrent, UnitOfApparentPower, UnitOfEnergy

from .const import DOMAIN, EVT_FRAME

async def async_setup_entry(hass, entry, async_add_entities):
    mgr = TeleinfoEntityManager(hass, entry, async_add_entities)
    await mgr.async_init()

class TeleinfoEntityManager:
    def __init__(self, hass, entry, async_add_entities):
        self.hass = hass
        self.entry = entry
        self.async_add_entities = async_add_entities
        self.entities: Dict[str, TeleinfoSensor] = {}
        self.dev_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name="Téléinfo Gateway")
        self.frames_count = 0
        self.status_entity = TeleinfoStatusSensor(f"{entry.entry_id}_status", "Statut Téléinfo", self.dev_info)
        self.entities[self.status_entity.unique_id] = self.status_entity

    async def async_init(self):
        # Add status entity immediately so something appears
        await self._async_add([self.status_entity])
        # Listen to incoming frames
        self.entry.async_on_unload(self.hass.bus.async_listen(EVT_FRAME, self._handle_frame))

    @callback
    def _handle_frame(self, event):
        frame: Dict[str, Any] = event.data.get("frame") or {}
        adco = frame.get("ADCO")
        device_info = self.dev_info
        if adco:
            device_info = DeviceInfo(identifiers={(DOMAIN, adco)}, name=f"Téléinfo {adco}")
            # update status sensor device if we now know ADCO
            self.status_entity.set_device_info(device_info)

        self.frames_count += 1
        self.status_entity.update_from_frame(self.frames_count, frame)

        mapping = {
            "PAPP": ("Puissance apparente", UnitOfApparentPower.VOLT_AMPERE, None),
            "IINST": ("Courant instantané", UnitOfElectricCurrent.AMPERE, None),
            "IMAX": ("Courant max", UnitOfElectricCurrent.AMPERE, None),
        }
        # Dynamic fields
        for key, (name, unit, device_class) in mapping.items():
            if key in frame:
                value = frame[key]
                # Try numeric when appropriate
                try:
                    if key in ("PAPP", "IINST", "IMAX"):
                        value = float(value)
                except Exception:
                    pass
                self._upsert(key, name, value, unit, device_class, device_info)

        # Energy indexes (Wh → expose kWh)
        for lbl, nice in [("BASE", "Index BASE"), ("HCHC", "Index HCHC"), ("HCHP", "Index HCHP")]:
            if lbl in frame:
                try:
                    val = float(frame[lbl])
                except Exception:
                    val = None
                if val is not None:
                    self._upsert(f"{lbl.lower()}_kwh", f"{nice} (kWh)", val/1000.0, UnitOfEnergy.KILO_WATT_HOUR, "energy", device_info)

    def _upsert(self, key: str, name: str, value: Any, unit: str | None, device_class: str | None, device_info: DeviceInfo):
        uid = f"{self.entry.entry_id}_{key}"
        ent = self.entities.get(uid)
        if not ent:
            ent = TeleinfoSensor(uid, name, unit, device_class, device_info)
            self.entities[uid] = ent
            # Add entity now
            self.hass.async_create_task(self._async_add([ent]))
        ent.set_native_value(value)

    async def _async_add(self, new: List[SensorEntity]):
        await self.async_add_entities(new)

class TeleinfoStatusSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:flash-triangle-outline"

    def __init__(self, unique_id: str, name: str, device_info: DeviceInfo):
        self._attr_unique_id = unique_id
        self._attr_name = name
        self._state = None
        self._attr_device_info = device_info
        self._attr_extra_state_attributes = {
            "frames": 0,
            "last_ptec": None,
            "last_seen": None,
        }

    @property
    def native_value(self):
        return self._state

    def set_device_info(self, device_info: DeviceInfo):
        self._attr_device_info = device_info

    def update_from_frame(self, count: int, frame: Dict[str, Any]):
        self._state = count
        self._attr_extra_state_attributes = {
            "frames": count,
            "last_ptec": frame.get("PTEC"),
            "last_seen": datetime.now().isoformat(timespec="seconds"),
        }
        if self.hass:
            self.async_write_ha_state()

class TeleinfoSensor(SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, unique_id: str, name: str, unit, device_class, device_info: DeviceInfo):
        self._attr_unique_id = unique_id
        self._attr_name = name
        self._state = None
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_device_info = device_info

    @property
    def native_value(self):
        return self._state

    def set_native_value(self, val):
        self._state = val
        if self.hass:
            self.async_write_ha_state()
