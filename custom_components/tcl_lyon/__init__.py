"""Intégration TCL Lyon : prochains départs en temps réel."""
from __future__ import annotations

from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import TclApi
from .const import DOMAIN
from .coordinator import TclCoordinator

PLATFORMS = [Platform.SENSOR]
CARD_URL = "/tcl_lyon/tcl-departures-card.js"
CARD_FILE = Path(__file__).parent / "frontend" / "tcl-departures-card.js"
LEAFLET_URL = "/tcl_lyon/leaflet"
LEAFLET_DIR = Path(__file__).parent / "frontend" / "leaflet"
VERSION = "1.4.8"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Sert la carte Lovelace et la charge automatiquement dans le frontend."""
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(CARD_URL, str(CARD_FILE), False),
            StaticPathConfig(LEAFLET_URL, str(LEAFLET_DIR), True),
        ]
    )
    add_extra_js_url(hass, f"{CARD_URL}?v={VERSION}")
    # Les WebView anciennes (Chrome < 131) reçoivent le frontend es5, qui a sa propre liste
    add_extra_js_url(hass, f"{CARD_URL}?v={VERSION}", es5=True)

    async def _activate_map(call: ServiceCall) -> None:
        """La carte des bus est ouverte : télécharger les positions pendant 60 s."""
        for entry in hass.config_entries.async_loaded_entries(DOMAIN):
            await entry.runtime_data.async_activate_positions(60)

    hass.services.async_register(DOMAIN, "activer_carte", _activate_map)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    api = TclApi(
        async_get_clientsession(hass), entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD]
    )
    coordinator = TclCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
