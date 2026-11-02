"""Coordinateur de mise à jour : passages (20 s), Vélo'v (60 s), alertes (5 min)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import TclApi, TclAuthError, TclError
from .const import (
    ALERTES_INTERVAL,
    CONF_STOP_ID,
    CONF_TRACKS,
    CONF_VELOV,
    CONF_VELOV_ID,
    DOMAIN,
    SCAN_INTERVAL,
    VELOV_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class TclCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """data = {"passages": {stop_id: [...]}, "alertes": [...] | None, "velov": {id: {...}}}"""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: TclApi) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL)
        self.api = api
        self.entry = entry
        self._alertes: list[dict] | None = None
        self._alertes_at = None
        self._alertes_failed = False
        self._velov: dict[str, dict] = {}
        self._velov_at = None

    async def _refresh_alertes(self, now) -> None:
        if self._alertes_at and now - self._alertes_at < ALERTES_INTERVAL:
            return
        self._alertes_at = now
        try:
            self._alertes = await self.api.async_get_alertes()
            self._alertes_failed = False
        except TclError as err:
            # Accès au jeu de données non demandé, etc. : on continue sans les alertes.
            if not self._alertes_failed:
                _LOGGER.warning("Alertes trafic TCL indisponibles : %s", err)
            self._alertes_failed = True

    async def _refresh_velov(self, now, ids: set[str]) -> None:
        if not ids or (self._velov_at and now - self._velov_at < VELOV_INTERVAL):
            return
        self._velov_at = now
        try:
            stations = await self.api.async_get_velov()
            self._velov = {s["id"]: s for s in stations if s["id"] in ids}
        except TclError as err:
            _LOGGER.warning("Vélo'v indisponible : %s", err)

    async def _async_update_data(self) -> dict[str, Any]:
        now = dt_util.utcnow()
        options = self.entry.options
        stop_ids = {t[CONF_STOP_ID] for t in options.get(CONF_TRACKS, [])}
        velov_ids = {v[CONF_VELOV_ID] for v in options.get(CONF_VELOV, [])}
        try:
            passages = await self.api.async_get_passages(stop_ids)
        except TclAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except TclError as err:
            raise UpdateFailed(str(err)) from err
        if stop_ids:
            await self._refresh_alertes(now)
        await self._refresh_velov(now, velov_ids)
        return {"passages": passages, "alertes": self._alertes, "velov": self._velov}
