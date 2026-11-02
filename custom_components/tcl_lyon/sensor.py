"""Capteurs : un par (arrêt, ligne, direction) suivi."""
from __future__ import annotations

import math
import re
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .api import bearing_deg, distance_m, line_base, normalize_text
from .const import (
    CONF_DIRECTION,
    CONF_VELOV,
    CONF_VELOV_ID,
    CONF_VELOV_NAME,
    CONF_LIGNE,
    CONF_MAP_BEARING,
    MAX_VEHICLE_DISTANCE_M,
    MAX_VEHICLES,
    CONF_STOP_ID,
    CONF_STOP_NAME,
    CONF_TRACKS,
    DOMAIN,
    MAX_DEPARTURES,
)
from .coordinator import TclCoordinator

PARIS = dt_util.get_time_zone("Europe/Paris")
_MIN_RE = re.compile(r"(\d+)\s*min", re.I)


def track_key(track: dict) -> str:
    return f"{track[CONF_STOP_ID]}_{track[CONF_LIGNE]}_{track.get(CONF_DIRECTION, '')}"


def _departure_time(p: dict, now: datetime) -> datetime | None:
    """Heure de départ : heurepassage si possible, sinon délai textuel."""
    if p["heure"]:
        parsed = dt_util.parse_datetime(p["heure"].replace(" ", "T", 1))
        if parsed is not None:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=PARIS)
            return parsed
    delai = p["delai"].lower()
    if m := _MIN_RE.search(delai):
        return now + timedelta(minutes=int(m.group(1)))
    if delai in ("proche", "imminent", "a l'approche", "à l'approche", "0 min"):
        return now
    return None


def _icon(ligne: str) -> str:
    up = ligne.upper()
    if up in ("A", "B", "C", "D"):
        return "mdi:subway-variant"
    if up.startswith("F"):
        return "mdi:gondola"
    if up.startswith("T") or up.startswith("RX"):
        return "mdi:tram"
    return "mdi:bus"


def _parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    parsed = dt_util.parse_datetime(value.replace(" ", "T", 1))
    if parsed is not None and parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=PARIS)
    return parsed


def active_alertes(alertes: list[dict] | None, ligne: str) -> list[dict]:
    """Alertes en cours concernant une ligne."""
    if not alertes:
        return []
    base = line_base(ligne)
    now = dt_util.now()
    out = []
    for a in alertes:
        if base not in a["lignes"]:
            continue
        debut, fin = _parse_dt(a["debut"]), _parse_dt(a["fin"])
        if (debut and debut > now) or (fin and fin < now):
            continue
        out.append(
            {k: a[k] for k in ("titre", "message", "type", "cause", "debut", "fin", "severite")}
        )
    # Les perturbations (sévérité 20) avant les simples informations (30, 40)
    out.sort(key=lambda x: (x["severite"], x["debut"]))
    return out


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", normalize_text(text)) if len(t) >= 3}


def _same_direction(a: str, b: str) -> bool:
    """Compare deux libellés de destination, avec tolérance (« V.Merle » / « Vivier Merle »)."""
    na, nb = normalize_text(a), normalize_text(b)
    if not na or not nb or na in nb or nb in na:
        return True
    ta, tb = _tokens(a), _tokens(b)
    return bool(ta and tb) and len(ta & tb) / min(len(ta), len(tb)) >= 0.5


def approaching_vehicles(
    vehicles: list[dict] | None,
    prev: dict[str, list[float]],
    stop: list[float] | None,
    ligne: str,
    direction: str,
    stop_id: str = "",
    courses: set[str] | None = None,
    destination_ids: set[str] | None = None,
) -> list[dict]:
    """Véhicules de la ligne qui se dirigent vers l'arrêt.

    Critères, du plus fiable au moins fiable :
    0. la course du véhicule figure dans les prochains passages annoncés à l'arrêt
       (DatedVehicleJourneyRef SIRI == coursetheorique) : il va forcément à l'arrêt ;
       idem si l'arrêt est son prochain arrêt annoncé ;
    1. sa destination est l'une de celles des passages suivis (sinon : autre sens) ;
    2. la distance à l'arrêt diminue depuis la mesure précédente ;
    3. sinon, le cap du véhicule pointe vers l'arrêt (écart < 100°).
    """
    courses = courses or set()
    destination_ids = destination_ids or set()
    if not vehicles or not stop:
        return []
    base = line_base(ligne)
    out = []
    for v in vehicles:
        if line_base(v["ligne"]) != base:
            continue
        pos = [v["lat"], v["lon"]]
        dist = distance_m(pos, stop)
        if dist > MAX_VEHICLE_DISTANCE_M:
            continue
        next_stops = v.get("prochains_arrets") or []
        if (v.get("course") and v["course"] in courses) or (stop_id and stop_id in next_stops):
            out.append({**v, "distance_m": round(dist), "confirme": True})
            continue
        if destination_ids and v.get("destination_id"):
            if v["destination_id"] not in destination_ids:
                continue  # autre sens
            # même destination : il reste à savoir s'il est avant ou après l'arrêt
        if direction and len(v["direction"]) > 2 and not v["direction"].isdigit():
            if not _same_direction(v["direction"], direction):
                continue
        approaching: bool | None = None
        if (p := prev.get(v["id"])) and p != pos:
            delta = dist - distance_m(p, stop)
            if abs(delta) > 25:
                approaching = delta < 0
        if approaching is None and v["cap"] is not None and dist > 80:
            diff = abs((bearing_deg(pos, stop) - v["cap"] + 180) % 360 - 180)
            approaching = diff < 100
        if approaching is False:
            continue
        out.append({**v, "distance_m": round(dist), "confirme": False})
    out.sort(key=lambda v: v["distance_m"])
    return out[:MAX_VEHICLES]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: TclCoordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        TclDepartureSensor(coordinator, entry, t) for t in entry.options.get(CONF_TRACKS, [])
    ]
    entities += [VelovSensor(coordinator, entry, v) for v in entry.options.get(CONF_VELOV, [])]
    async_add_entities(entities)


class TclDepartureSensor(CoordinatorEntity[TclCoordinator], SensorEntity):
    _attr_has_entity_name = True
    # Attributs volumineux et changeant toutes les 20 s : exclus de l'historique (recorder)
    # pour ne pas faire grossir la base ni user la mémoire eMMC (Home Assistant Green).
    _unrecorded_attributes = frozenset(
        {"departs", "alertes", "vehicules", "arret_position", "carte_active",
         "carte_disponible", "carte_orientation", "positions_ligne"}
    )
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_attribution = "Données TCL / SYTRAL via data.grandlyon.com"

    def __init__(self, coordinator: TclCoordinator, entry: ConfigEntry, track: dict) -> None:
        super().__init__(coordinator)
        self._track = track
        self._entry = entry
        self._ligne = track[CONF_LIGNE]
        self._direction = track.get(CONF_DIRECTION, "")
        self._stop_id = track[CONF_STOP_ID]
        self._stop_name = track.get(CONF_STOP_NAME, self._stop_id)
        self._attr_unique_id = f"{entry.entry_id}_{track_key(track)}"
        self._attr_name = f"{self._ligne} → {self._direction or 'toutes directions'}"
        self._attr_icon = _icon(self._ligne)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{self._stop_id}")},
            name=f"Arrêt TCL {self._stop_name}",
            manufacturer="TCL / SYTRAL",
            model=f"Arrêt {self._stop_id}",
            entry_type=DeviceEntryType.SERVICE,
        )

    def _departures(self) -> list[dict[str, Any]]:
        now = dt_util.now()
        passages = (self.coordinator.data or {}).get("passages", {}).get(self._stop_id, [])
        out = []
        for p in passages:
            if p["ligne"] != self._ligne:
                continue
            if self._direction and p["direction"] != self._direction:
                continue
            when = _departure_time(p, now)
            if when is None or when < now - timedelta(seconds=60):
                continue
            out.append(
                {
                    "heure": when.isoformat(),
                    "minutes": max(0, math.floor((when - now).total_seconds() / 60)),
                    "temps_reel": p["temps_reel"],
                    "delai": p["delai"],
                    "direction": p["direction"],
                }
            )
        out.sort(key=lambda d: d["heure"])
        return out[:MAX_DEPARTURES]

    @property
    def native_value(self) -> int | None:
        deps = self._departures()
        return deps[0]["minutes"] if deps else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "integration": DOMAIN,
            "type": "depart",
            "ligne": self._ligne,
            "direction": self._direction or None,
            "arret": self._stop_name,
            "arret_id": self._stop_id,
            "departs": self._departures(),
            "alertes": active_alertes((self.coordinator.data or {}).get("alertes"), self._ligne),
            **self._map_attributes(),
        }

    def _map_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or {}
        if data.get("vehicules") is None:
            return {"carte_disponible": False}
        stop = data.get("stops", {}).get(self._stop_id)
        passages = [
            p
            for p in data.get("passages", {}).get(self._stop_id, [])
            if p["ligne"] == self._ligne
            and (not self._direction or p["direction"] == self._direction)
        ]
        base = line_base(self._ligne)
        return {
            "carte_disponible": stop is not None,
            "arret_position": stop,
            "carte_orientation": self._entry.options.get(CONF_MAP_BEARING, 0),
            # Faux pour le métro et le funiculaire, absents du flux de positions
            "carte_active": data.get("carte_active", False),
            "positions_ligne": not data.get("carte_active") or any(line_base(v["ligne"]) == base for v in data["vehicules"]),
            "vehicules": [
                {k: v[k] for k in ("id", "lat", "lon", "cap", "distance_m", "confirme")}
                for v in approaching_vehicles(
                    data["vehicules"], data.get("vehicules_prev", {}), stop,
                    self._ligne, self._direction, self._stop_id,
                    {p["course"] for p in passages if p.get("course")},
                    {p["destination_id"] for p in passages if p.get("destination_id")},
                )
            ],
        }


class VelovSensor(CoordinatorEntity[TclCoordinator], SensorEntity):
    """Nombre de vélos disponibles dans une station Vélo'v."""

    _unrecorded_attributes = frozenset({"maj", "statut", "velos_mecaniques", "places"})

    _attr_has_entity_name = True
    _attr_icon = "mdi:bicycle"
    _attr_native_unit_of_measurement = "vélos"
    _attr_attribution = "Données Vélo'v / JCDecaux via data.grandlyon.com"

    def __init__(self, coordinator: TclCoordinator, entry: ConfigEntry, station: dict) -> None:
        super().__init__(coordinator)
        self._id = station[CONF_VELOV_ID]
        self._name = station.get(CONF_VELOV_NAME, self._id)
        self._attr_unique_id = f"{entry.entry_id}_velov_{self._id}"
        self._attr_name = "Vélos disponibles"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_velov_{self._id}")},
            name=f"Vélo'v {self._name}",
            manufacturer="Vélo'v / JCDecaux",
            model=f"Station {self._id}",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def _station(self) -> dict | None:
        return (self.coordinator.data or {}).get("velov", {}).get(self._id)

    @property
    def available(self) -> bool:
        return super().available and self._station is not None

    @property
    def native_value(self) -> int | None:
        st = self._station
        return st["velos"] if st else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        st = self._station or {}
        return {
            "integration": DOMAIN,
            "type": "velov",
            "station": self._name,
            "station_id": self._id,
            **{k: st.get(k) for k in (
                "places", "capacite", "velos_electriques", "velos_mecaniques", "statut", "maj"
            )},
        }
