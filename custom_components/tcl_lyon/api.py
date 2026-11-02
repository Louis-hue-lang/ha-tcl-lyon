"""Client minimal pour l'API temps réel TCL (data.grandlyon.com)."""
from __future__ import annotations

import asyncio
import logging
import unicodedata
from typing import Any

import aiohttp

from .const import URL_ARRETS, URL_PASSAGES

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

    async def _get_json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            async with self._session.get(
                url, params=params, auth=self._auth, timeout=TIMEOUT
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
