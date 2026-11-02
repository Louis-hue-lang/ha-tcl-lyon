"""Client minimal pour l'API temps réel TCL (data.grandlyon.com)."""
from __future__ import annotations

import asyncio
import logging
import unicodedata
from typing import Any

import aiohttp

import json
import re

import math

from .const import URL_ALERTES, URL_ARRETS, URL_PASSAGES, URL_VELOV

_LOGGER = logging.getLogger(__name__)

PAGE_SIZE = 1000
MAX_PAGES = 60
TIMEOUT = aiohttp.ClientTimeout(total=30)


class TclError(Exception):
    """Erreur générique."""


class TclAuthError(TclError):
    """Identifiants refusés ou accès au jeu de données non accordé."""


def normalize_text(value: str) -> str:
    """Minuscule et sans accents, pour la recherche."""
    value = unicodedata.normalize("NFKD", value or "")
    return "".join(c for c in value if not unicodedata.combining(c)).lower().strip()


_SUFFIX_RE = re.compile(r"^(.*\d)[AR]$")


def line_base(ligne: str) -> str:
    """Code commercial sans le suffixe de sens éventuel : « C13A » -> « C13 », « A » -> « A »."""
    ligne = (ligne or "").strip().upper()
    m = _SUFFIX_RE.match(ligne)
    return m.group(1) if m else ligne


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_alerte(rec: dict[str, Any]) -> dict[str, Any]:
    lignes = {
        line_base(str(rec.get(k, "") or ""))
        for k in ("ligne_com", "ligne_cli", "ligne")
        if rec.get(k)
    }
    return {
        "lignes": sorted(lignes),
        "mode": str(rec.get("mode", "") or ""),
        "type": str(rec.get("type", "") or ""),
        "cause": str(rec.get("cause", "") or ""),
        "titre": str(rec.get("titre", "") or "").strip(),
        "message": str(rec.get("message", "") or "").strip(),
        "debut": str(rec.get("debut", "") or ""),
        "fin": str(rec.get("fin", "") or ""),
    }


def parse_velov(rec: dict[str, Any]) -> dict[str, Any]:
    """Station Vélo'v ; formats plat, « total_stands » et Feature GeoJSON (WFS)."""
    if isinstance(rec.get("properties"), dict):
        rec = rec["properties"]
    total = rec.get("total_stands")
    if isinstance(total, str):
        try:
            total = json.loads(total)
        except ValueError:
            total = None
    avail = (total or {}).get("availabilities", {}) if isinstance(total, dict) else {}
    bikes = _int(rec.get("available_bikes"))
    if bikes is None:
        bikes = _int(avail.get("bikes"))
    stands = _int(rec.get("available_bike_stands"))
    if stands is None:
        stands = _int(avail.get("stands"))
    capacity = _int(rec.get("bike_stands"))
    if capacity is None and isinstance(total, dict):
        capacity = _int(total.get("capacity"))
    return {
        "id": str(rec.get("number", rec.get("idstation", rec.get("gid", "")))).strip(),
        "nom": str(rec.get("name", rec.get("nom", "")) or "").strip(),
        "adresse": str(rec.get("address", rec.get("adresse", "")) or "").strip(),
        "velos": bikes,
        "velos_electriques": _int(avail.get("electricalBikes")),
        "velos_mecaniques": _int(avail.get("mechanicalBikes")),
        "places": stands,
        "capacite": capacity,
        "statut": str(rec.get("status", "") or ""),
        "maj": str(rec.get("last_update", "") or ""),
    }


_LAT_KEYS = ("lat", "latitude", "y", "coord_y")
_LON_KEYS = ("lon", "lng", "long", "longitude", "x", "coord_x")
_VEH_LINE_KEYS = ("ligne", "ligne_com", "ligne_cli", "line", "lineref", "route_id", "idligne", "code_ligne")
_VEH_DIR_KEYS = ("direction", "destination", "destinationname", "direction_name", "sens", "terminus")
_VEH_BEARING_KEYS = ("cap", "bearing", "heading", "orientation", "angle", "azimut")
_VEH_ID_KEYS = ("id", "vehicule", "vehicle_id", "idvehicule", "vehiclelabel", "numero", "parc", "gid")


def _float(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _first(rec: dict, keys: tuple[str, ...]) -> Any:
    lower = {k.lower(): v for k, v in rec.items()}
    for k in keys:
        if lower.get(k) not in (None, ""):
            return lower[k]
    return None


def extract_latlon(rec: dict[str, Any]) -> list[float] | None:
    """[lat, lon] en WGS84, depuis des champs plats ou une géométrie GeoJSON."""
    geom = rec.get("geometry") or rec.get("geom") or rec.get("the_geom")
    if isinstance(geom, str):
        try:
            geom = json.loads(geom)
        except ValueError:
            geom = None
    if isinstance(geom, dict) and isinstance(geom.get("coordinates"), list):
        coords = geom["coordinates"]
        while coords and isinstance(coords[0], list):  # Multipoint -> premier point
            coords = coords[0]
        if len(coords) >= 2:
            lon, lat = _float(coords[0]), _float(coords[1])
            if lat is not None and lon is not None and abs(lat) <= 90 and abs(lon) <= 180:
                return [lat, lon]
    lat, lon = _float(_first(rec, _LAT_KEYS)), _float(_first(rec, _LON_KEYS))
    if lat is None or lon is None or abs(lat) > 90 or abs(lon) > 180:
        return None  # absent ou dans une projection non géographique
    return [lat, lon]


def parse_vehicle(rec: dict[str, Any]) -> dict[str, Any] | None:
    """Uniformise une position de véhicule ; formats rdata, GeoJSON ou GTFS-RT JSON."""
    if isinstance(rec.get("properties"), dict):  # Feature GeoJSON
        rec = {**rec["properties"], "geometry": rec.get("geometry")}
    if isinstance(rec.get("vehicle"), dict):  # GTFS-RT converti en JSON
        v = rec["vehicle"]
        pos, trip = v.get("position", {}), v.get("trip", {})
        rec = {
            "id": (v.get("vehicle") or {}).get("id") or rec.get("id"),
            "lat": pos.get("latitude"),
            "lon": pos.get("longitude"),
            "bearing": pos.get("bearing"),
            "route_id": trip.get("routeId") or trip.get("route_id"),
            "direction": trip.get("directionId", trip.get("direction_id")),
        }
    position = extract_latlon(rec)
    if position is None:
        return None
    bearing = _float(_first(rec, _VEH_BEARING_KEYS))
    return {
        "prochains_arrets": [],
        "id": str(_first(rec, _VEH_ID_KEYS) or f"{position[0]:.5f},{position[1]:.5f}"),
        "ligne": str(_first(rec, _VEH_LINE_KEYS) or "").strip(),
        "direction": str(_first(rec, _VEH_DIR_KEYS) or "").strip(),
        "cap": bearing % 360 if bearing is not None else None,
        "lat": position[0],
        "lon": position[1],
    }


def _sv(value: Any) -> str:
    """Valeur SIRI : chaîne, {"value": ...} ou liste de ceux-ci."""
    if isinstance(value, list):
        value = value[0] if value else ""
    if isinstance(value, dict):
        value = value.get("value", "")
    return str(value or "").strip()


def _siri_line(journey: dict[str, Any]) -> str:
    """Code de ligne : PublishedLineName, sinon extrait de LineRef (« ActIV:Line::C3:SYTRAL »)."""
    name = _sv(journey.get("PublishedLineName"))
    if name:
        return name
    ref = _sv(journey.get("LineRef"))
    if "::" in ref:
        return ref.split("::", 1)[1].split(":", 1)[0]
    parts = [p for p in ref.split(":") if p and p.lower() != "line"]
    return parts[1] if len(parts) >= 3 else (parts[-1] if parts else "")


_DIGITS_RE = re.compile(r"\d{3,}")


def _stop_ids(ref: str) -> set[str]:
    """Identifiants numériques d'un StopPointRef (« ActIV:StopPoint:BP:30170:SYTRAL » -> 30170)."""
    return set(_DIGITS_RE.findall(ref or ""))


def parse_siri_vm(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Positions depuis un flux SIRI Lite VehicleMonitoring."""
    siri = data.get("Siri", data)
    deliveries = (siri.get("ServiceDelivery") or {}).get("VehicleMonitoringDelivery") or []
    if isinstance(deliveries, dict):
        deliveries = [deliveries]
    out = []
    for delivery in deliveries:
        for act in delivery.get("VehicleActivity") or []:
            j = act.get("MonitoredVehicleJourney") or {}
            loc = j.get("VehicleLocation") or {}
            lat, lon = _float(loc.get("Latitude")), _float(loc.get("Longitude"))
            if lat is None or lon is None:
                continue
            next_stops: set[str] = set()
            if isinstance(j.get("MonitoredCall"), dict):
                next_stops |= _stop_ids(_sv(j["MonitoredCall"].get("StopPointRef")))
            onward = j.get("OnwardCalls") or {}
            for call in onward.get("OnwardCall", []) if isinstance(onward, dict) else onward:
                if isinstance(call, dict):
                    next_stops |= _stop_ids(_sv(call.get("StopPointRef")))
            bearing = _float(j.get("Bearing"))
            vid = _sv(j.get("VehicleRef")) or _sv(act.get("ItemIdentifier")) or f"{lat:.5f},{lon:.5f}"
            out.append(
                {
                    "id": vid,
                    "ligne": _siri_line(j),
                    "direction": _sv(j.get("DestinationName")),
                    "cap": bearing % 360 if bearing is not None else None,
                    "lat": lat,
                    "lon": lon,
                    "prochains_arrets": sorted(next_stops),
                }
            )
    return out


def distance_m(a: list[float], b: list[float]) -> float:
    """Distance en mètres entre deux points [lat, lon]."""
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(h))


def bearing_deg(a: list[float], b: list[float]) -> float:
    """Cap (0 = nord) pour aller de a vers b."""
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    y = math.sin(lon2 - lon1) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def parse_passage(rec: dict[str, Any]) -> dict[str, Any]:
    """Uniformise un enregistrement de passage."""
    return {
        "stop_id": str(rec.get("id", "")).strip(),
        "ligne": str(rec.get("ligne", "")).strip(),
        "direction": str(rec.get("direction", "")).strip(),
        "delai": str(rec.get("delaipassage", "") or "").strip(),
        "heure": str(rec.get("heurepassage", "") or "").strip(),
        "temps_reel": str(rec.get("type", "")).upper() == "E",
    }


class TclApi:
    """Accès aux jeux de données TCL."""

    def __init__(self, session: aiohttp.ClientSession, username: str, password: str) -> None:
        self._session = session
        self._auth = aiohttp.BasicAuth(username, password)
        self._stops: list[dict[str, Any]] | None = None
        # None = inconnu ; True/False une fois testé
        self._filter_supported: bool | None = None

    async def _get_json(
        self, url: str, params: dict[str, Any], auth: bool = True
    ) -> dict[str, Any]:
        try:
            async with self._session.get(
                url, params=params or None, auth=self._auth if auth else None, timeout=TIMEOUT
            ) as resp:
                if resp.status in (401, 403):
                    raise TclAuthError(f"Accès refusé ({resp.status})")
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise TclError(f"Erreur réseau : {err}") from err

    async def _get_all(self, url: str, params: dict[str, Any] | None = None) -> list[dict]:
        """Récupère toutes les pages d'un jeu de données."""
        results: list[dict] = []
        start = 1
        first_seen = None
        for _ in range(MAX_PAGES):
            page_params = {**(params or {}), "maxfeatures": PAGE_SIZE, "start": start}
            data = await self._get_json(url, page_params)
            values = data.get("values", []) if isinstance(data, dict) else []
            if not values:
                break
            marker = repr(values[0])
            if marker == first_seen:  # la pagination est ignorée : on s'arrête
                break
            first_seen = first_seen or marker
            results.extend(values)
            if len(values) < PAGE_SIZE:
                break
            start += PAGE_SIZE
        return results

    async def async_validate(self) -> None:
        """Vérifie les identifiants et l'accès au jeu de données temps réel."""
        await self._get_json(URL_PASSAGES, {"maxfeatures": 1, "start": 1})

    async def async_get_stops(self) -> list[dict[str, Any]]:
        """Liste des arrêts (mise en cache)."""
        if self._stops is None:
            raw = await self._get_all(URL_ARRETS)
            self._stops = [
                {
                    "id": str(r.get("id", "")).strip(),
                    "nom": str(r.get("nom", "")).strip(),
                    "desserte": str(r.get("desserte", "") or ""),
                    "position": extract_latlon(r),
                }
                for r in raw
                if r.get("id") is not None
            ]
        return self._stops

    async def async_search_stops(self, query: str) -> list[dict[str, Any]]:
        q = normalize_text(query)
        stops = await self.async_get_stops()
        found = [s for s in stops if q in normalize_text(s["nom"]) or q == s["id"]]
        return sorted(found, key=lambda s: (s["nom"], s["id"]))[:60]

    async def async_get_passages(self, stop_ids: set[str]) -> dict[str, list[dict]]:
        """Passages groupés par arrêt."""
        result: dict[str, list[dict]] = {sid: [] for sid in stop_ids}
        if not stop_ids:
            return result

        if self._filter_supported is not False:
            try:
                for sid in stop_ids:
                    raw = await self._get_all(URL_PASSAGES, {"field": "id", "value": sid})
                    recs = [parse_passage(r) for r in raw]
                    if any(r["stop_id"] != sid for r in recs):
                        # Le filtre côté serveur n'est pas appliqué
                        raise ValueError("filtre ignoré")
                    result[sid] = recs
                self._filter_supported = True
                return result
            except ValueError:
                _LOGGER.debug("Filtre serveur non supporté, téléchargement complet")
                self._filter_supported = False

        for rec in await self._get_all(URL_PASSAGES):
            p = parse_passage(rec)
            if p["stop_id"] in result:
                result[p["stop_id"]].append(p)
        return result

    async def async_get_alertes(self) -> list[dict[str, Any]]:
        """Alertes TCL + lignes scolaires ; une source inaccessible est ignorée."""
        alertes: list[dict[str, Any]] = []
        errors: list[TclError] = []
        for url in URL_ALERTES:
            try:
                alertes += [parse_alerte(r) for r in await self._get_all(url)]
            except TclError as err:
                _LOGGER.debug("Alertes indisponibles (%s) : %s", url, err)
                errors.append(err)
        if len(errors) == len(URL_ALERTES):
            raise errors[0]
        return alertes

    async def async_get_velov(self) -> list[dict[str, Any]]:
        data = await self._get_json(URL_VELOV, {}, auth=False)
        raw = data.get("features") or data.get("values") or [] if isinstance(data, dict) else data
        stations = [parse_velov(r) for r in raw if isinstance(r, dict)]
        return [s for s in stations if s["id"]]

    async def async_search_velov(self, query: str) -> list[dict[str, Any]]:
        q = normalize_text(query)
        found = [
            s
            for s in await self.async_get_velov()
            if q in normalize_text(s["nom"]) or q in normalize_text(s["adresse"]) or q == s["id"]
        ]
        return sorted(found, key=lambda s: s["nom"])[:60]

    async def async_get_stop(self, stop_id: str) -> dict[str, Any] | None:
        return next((s for s in await self.async_get_stops() if s["id"] == stop_id), None)

    async def async_get_vehicles(self, url: str) -> list[dict[str, Any]]:
        """Positions des véhicules depuis l'URL configurée."""
        if "/ws/rdata/" in url and "maxfeatures" not in url:
            raw: Any = await self._get_all(url)
        else:
            raw = await self._get_json(url, {})
        if isinstance(raw, dict):
            if "Siri" in raw or "ServiceDelivery" in raw:
                return parse_siri_vm(raw)
            raw = raw.get("values") or raw.get("features") or raw.get("entity") or []
        vehicles = [parse_vehicle(r) for r in raw if isinstance(r, dict)]
        return [v for v in vehicles if v]
