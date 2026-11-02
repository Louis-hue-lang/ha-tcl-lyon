"""Coordinateur de mise à jour."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import TclApi, TclAuthError, TclError
from .const import CONF_STOP_ID, CONF_TRACKS, DOMAIN, SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class TclCoordinator(DataUpdateCoordinator[dict[str, list[dict]]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, api: TclApi) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL)
        self.api = api
        self.entry = entry

    async def _async_update_data(self) -> dict[str, list[dict]]:
        stop_ids = {t[CONF_STOP_ID] for t in self.entry.options.get(CONF_TRACKS, [])}
        try:
            return await self.api.async_get_passages(stop_ids)
        except TclAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except TclError as err:
            raise UpdateFailed(str(err)) from err
