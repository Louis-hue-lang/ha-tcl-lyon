"""Configuration via l'interface : identifiants puis arrêts/lignes/directions."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import TclApi, TclAuthError, TclError
from .const import (
    CONF_DIRECTION,
    CONF_LIGNE,
    CONF_STOP_ID,
    CONF_STOP_NAME,
    CONF_TRACKS,
    CONF_VELOV,
    CONF_VELOV_ID,
    CONF_VELOV_NAME,
    DOMAIN,
)

SEP = "␟"  # séparateur interne ligne/direction

CREDS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): TextSelector(TextSelectorConfig(type=TextSelectorType.EMAIL)),
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)


async def _validate(hass, data: dict) -> dict[str, str]:
    api = TclApi(async_get_clientsession(hass), data[CONF_USERNAME], data[CONF_PASSWORD])
    try:
        await api.async_validate()
    except TclAuthError:
        return {"base": "invalid_auth"}
    except TclError:
        return {"base": "cannot_connect"}
    return {}


class TclConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_USERNAME].lower())
            self._abort_if_unique_id_configured()
            errors = await _validate(self.hass, user_input)
            if not errors:
                return self.async_create_entry(
                    title="TCL Lyon", data=user_input, options={CONF_TRACKS: [], CONF_VELOV: []}
                )
        return self.async_show_form(step_id="user", data_schema=CREDS_SCHEMA, errors=errors)

    async def async_step_reauth(self, entry_data: dict) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await _validate(self.hass, user_input)
            if not errors:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(), data_updates=user_input
                )
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=CREDS_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return TclOptionsFlow()


class TclOptionsFlow(OptionsFlow):
    """Ajout / suppression des lignes suivies."""

    def __init__(self) -> None:
        self._tracks: list[dict] | None = None
        self._velov: list[dict] | None = None
        self._velov_matches: list[dict] = []
        self._matches: list[dict] = []
        self._stop: dict | None = None
        self._api: TclApi | None = None

    @property
    def tracks(self) -> list[dict]:
        if self._tracks is None:
            self._tracks = list(self.config_entry.options.get(CONF_TRACKS, []))
        return self._tracks

    @property
    def velov(self) -> list[dict]:
        if self._velov is None:
            self._velov = list(self.config_entry.options.get(CONF_VELOV, []))
        return self._velov

    @property
    def api(self) -> TclApi:
        if self._api is None:
            self._api = TclApi(
                async_get_clientsession(self.hass),
                self.config_entry.data[CONF_USERNAME],
                self.config_entry.data[CONF_PASSWORD],
            )
        return self._api

    def _save(self) -> ConfigFlowResult:
        return self.async_create_entry(data={CONF_TRACKS: self.tracks, CONF_VELOV: self.velov})

    async def async_step_init(self, user_input: dict | None = None) -> ConfigFlowResult:
        menu = ["search", "velov_search"]
        if self.tracks or self.velov:
            menu.append("remove")
        return self.async_show_menu(
            step_id="init",
            menu_options=menu,
            description_placeholders={
                "tracks": "\n".join(
                    f"- {t[CONF_STOP_NAME]} : {t[CONF_LIGNE]} → "
                    f"{t.get(CONF_DIRECTION) or 'toutes directions'}"
                    for t in self.tracks
                )
                + "".join(f"\n- Vélo'v {v[CONF_VELOV_NAME]}" for v in self.velov)
                or "(aucune)"
            },
        )

    async def async_step_search(self, user_input: dict | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                self._matches = await self.api.async_search_stops(user_input["query"])
            except TclAuthError:
                errors["base"] = "invalid_auth"
            except TclError:
                errors["base"] = "cannot_connect"
            else:
                if self._matches:
                    return await self.async_step_stop()
                errors["base"] = "no_stop"
        return self.async_show_form(
            step_id="search",
            data_schema=vol.Schema({vol.Required("query"): TextSelector()}),
            errors=errors,
        )

    async def async_step_stop(self, user_input: dict | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._stop = next(s for s in self._matches if s["id"] == user_input[CONF_STOP_ID])
            return await self.async_step_lines()
        options = [
            SelectOptionDict(
                value=s["id"],
                label=f"{s['nom']} (#{s['id']})"
                + (f" — {s['desserte']}" if s["desserte"] else ""),
            )
            for s in self._matches
        ]
        return self.async_show_form(
            step_id="stop",
            data_schema=vol.Schema(
                {vol.Required(CONF_STOP_ID): SelectSelector(SelectSelectorConfig(options=options))}
            ),
        )

    async def async_step_lines(self, user_input: dict | None = None) -> ConfigFlowResult:
        assert self._stop is not None
        stop_id, stop_name = self._stop["id"], self._stop["nom"]
        errors: dict[str, str] = {}

        if user_input is not None:
            existing = {(t[CONF_STOP_ID], t[CONF_LIGNE], t.get(CONF_DIRECTION, "")) for t in self.tracks}
            for choice in user_input.get("choices", []):
                ligne, _, direction = choice.partition(SEP)
                if (stop_id, ligne, direction) in existing:
                    continue
                self.tracks.append(
                    {
                        CONF_STOP_ID: stop_id,
                        CONF_STOP_NAME: stop_name,
                        CONF_LIGNE: ligne,
                        CONF_DIRECTION: direction,
                    }
                )
            return self._save()

        try:
            passages = (await self.api.async_get_passages({stop_id}))[stop_id]
        except TclError:
            passages = []
            errors["base"] = "cannot_connect"

        combos = sorted({(p["ligne"], p["direction"]) for p in passages if p["ligne"]})
        lignes = sorted({c[0] for c in combos})
        # Lignes desservies d'après le référentiel (utile la nuit, quand il n'y a aucun passage)
        for item in self._stop["desserte"].split(","):
            ligne = item.split(":")[0].strip()
            if ligne and ligne not in lignes:
                lignes.append(ligne)

        options = [
            SelectOptionDict(value=f"{l}{SEP}{d}", label=f"Ligne {l} → {d}") for l, d in combos
        ] + [
            SelectOptionDict(value=f"{l}{SEP}", label=f"Ligne {l} → toutes directions")
            for l in lignes
        ]
        if not options:
            errors["base"] = "no_line"

        return self.async_show_form(
            step_id="lines",
            data_schema=vol.Schema(
                {
                    vol.Required("choices", default=[]): SelectSelector(
                        SelectSelectorConfig(
                            options=options, multiple=True, mode=SelectSelectorMode.LIST
                        )
                    )
                }
            ),
            errors=errors,
            description_placeholders={"stop": stop_name},
        )

    async def async_step_remove(self, user_input: dict | None = None) -> ConfigFlowResult:
        keys = [
            f"{t[CONF_STOP_ID]}{SEP}{t[CONF_LIGNE]}{SEP}{t.get(CONF_DIRECTION, '')}"
            for t in self.tracks
        ]
        if user_input is not None:
            to_remove = set(user_input.get("remove", []))
            self._tracks = [t for t, k in zip(self.tracks, keys) if k not in to_remove]
            self._velov = [v for v in self.velov if f"velov{SEP}{v[CONF_VELOV_ID]}" not in to_remove]
            return self._save()
        options = [
            SelectOptionDict(
                value=k,
                label=f"{t[CONF_STOP_NAME]} : {t[CONF_LIGNE]} → "
                f"{t.get(CONF_DIRECTION) or 'toutes directions'}",
            )
            for t, k in zip(self.tracks, keys)
        ] + [
            SelectOptionDict(
                value=f"velov{SEP}{v[CONF_VELOV_ID]}", label=f"Vélo'v {v[CONF_VELOV_NAME]}"
            )
            for v in self.velov
        ]
        return self.async_show_form(
            step_id="remove",
            data_schema=vol.Schema(
                {
                    vol.Required("remove", default=[]): SelectSelector(
                        SelectSelectorConfig(
                            options=options, multiple=True, mode=SelectSelectorMode.LIST
                        )
                    )
                }
            ),
        )

    async def async_step_velov_search(self, user_input: dict | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                self._velov_matches = await self.api.async_search_velov(user_input["query"])
            except TclError:
                errors["base"] = "cannot_connect"
            else:
                if self._velov_matches:
                    return await self.async_step_velov_station()
                errors["base"] = "no_station"
        return self.async_show_form(
            step_id="velov_search",
            data_schema=vol.Schema({vol.Required("query"): TextSelector()}),
            errors=errors,
        )

    async def async_step_velov_station(self, user_input: dict | None = None) -> ConfigFlowResult:
        if user_input is not None:
            known = {v[CONF_VELOV_ID] for v in self.velov}
            for sid in user_input.get("stations", []):
                st = next((s for s in self._velov_matches if s["id"] == sid), None)
                if st and sid not in known:
                    self.velov.append({CONF_VELOV_ID: sid, CONF_VELOV_NAME: st["nom"]})
            return self._save()
        options = [
            SelectOptionDict(
                value=s["id"],
                label=f"{s['nom']} (#{s['id']})"
                + (f" — {s['velos']} vélos / {s['places']} places" if s["velos"] is not None else ""),
            )
            for s in self._velov_matches
        ]
        return self.async_show_form(
            step_id="velov_station",
            data_schema=vol.Schema(
                {
                    vol.Required("stations", default=[]): SelectSelector(
                        SelectSelectorConfig(
                            options=options, multiple=True, mode=SelectSelectorMode.LIST
                        )
                    )
                }
            ),
        )
