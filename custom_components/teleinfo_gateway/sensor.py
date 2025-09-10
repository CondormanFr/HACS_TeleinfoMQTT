
from __future__ import annotations
from typing import Any, Dict
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.const import UnitOfElectricCurrent, UnitOfApparentPower, UnitOfEnergy

from .const import DOMAIN, EVT_FRAME

async def async_setup_entry(hass, entry, async_add_entities):
    mgr = TeleinfoEntityManager(hass, entry)
    async_add_entities(mgr.entities.values())

class TeleinfoEntityManager:
    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self.entities: Dict[str, TeleinfoSensor] = {}
        self.dev_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name="Téléinfo Gateway")
        entry.async_on_unload(self.hass.bus.async_listen(EVT_FRAME, self._handle_frame))

    @callback
    def _handle_frame(self, event):
        frame: Dict[str, Any] = event.data.get("frame") or {}
        adco = frame.get("ADCO")
        device_info = self.dev_info
        if adco:
            device_info = DeviceInfo(identifiers={(DOMAIN, adco)}, name=f"Téléinfo {adco}")
        mapping = {
            "PAPP": ("Puissance apparente", UnitOfApparentPower.VOLT_AMPERE, None),
            "IINST": ("Courant instantané", UnitOfElectricCurrent.AMPERE, None),
            "IMAX": ("Courant max", UnitOfElectricCurrent.AMPERE, None),
        }
        # Dynamic fields
        for key, (name, unit, device_class) in mapping.items():
            if key in frame:
                self._upsert(key, name, frame[key], unit, device_class, device_info)
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
        eid = f"{self.entry.entry_id}_{key}"
        ent = self.entities.get(eid)
        if not ent:
            ent = TeleinfoSensor(eid, name, unit, device_class, device_info)
            self.entities[eid] = ent
            self.hass.async_create_task(self._async_add([ent]))
        ent.set_native_value(value)

    async def _async_add(self, new):
        from homeassistant.helpers.entity_platform import async_get_current_platform
        platform = async_get_current_platform()
        await platform.async_add_entities(new)

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
