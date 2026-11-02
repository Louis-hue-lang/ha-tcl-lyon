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

from .const import (
    CONF_DIRECTION,
    CONF_LIGNE,
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


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: TclCoordinator = entry.runtime_data
    async_add_entities(
        TclDepartureSensor(coordinator, entry, t) for t in entry.options.get(CONF_TRACKS, [])
    )


class TclDepartureSensor(CoordinatorEntity[TclCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_attribution = "Données TCL / SYTRAL via data.grandlyon.com"

    def __init__(self, coordinator: TclCoordinator, entry: ConfigEntry, track: dict) -> None:
        super().__init__(coordinator)
        self._track = track
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
        passages = (self.coordinator.data or {}).get(self._stop_id, [])
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
            "ligne": self._ligne,
            "direction": self._direction or None,
            "arret": self._stop_name,
            "arret_id": self._stop_id,
            "departs": self._departures(),
        }
