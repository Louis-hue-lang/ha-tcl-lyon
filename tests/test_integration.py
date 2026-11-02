"""Tests de bout en bout avec un faux serveur data.grandlyon.com."""
from datetime import timedelta
import re

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.tcl_lyon.api import parse_siri_vm, parse_velov, line_base
from custom_components.tcl_lyon.const import (
    DOMAIN, URL_ALERTES, URL_ARRETS, URL_PASSAGES, URL_POSITIONS, URL_VELOV,
)
from custom_components.tcl_lyon.sensor import approaching_vehicles

STOP = {"id": 30170, "nom": "Part-Dieu Vivier Merle", "desserte": "C3:A,C3:R,86:A", "lon": 4.8597, "lat": 45.7605}


def _fmt(minutes):
    return (dt_util.now() + timedelta(minutes=minutes)).astimezone(
        dt_util.get_time_zone("Europe/Paris")).strftime("%Y-%m-%d %H:%M:%S")


def passages():
    return {"values": [
        {"id": 30170, "ligne": "C3A", "direction": "Gare Saint-Paul", "delaipassage": "2 min", "heurepassage": _fmt(2), "type": "E"},
        {"id": 30170, "ligne": "C3A", "direction": "Gare Saint-Paul", "delaipassage": "9 min", "heurepassage": _fmt(9), "type": "T"},
        {"id": 30170, "ligne": "86A", "direction": "La Doua", "delaipassage": "Proche", "heurepassage": _fmt(0), "type": "E"},
    ]}


SIRI = {"Siri": {"ServiceDelivery": {"VehicleMonitoringDelivery": [{"VehicleActivity": [
    # approche, annonce l'arrêt dans ses prochains arrêts
    {"MonitoredVehicleJourney": {"LineRef": {"value": "ActIV:Line::C3:SYTRAL"}, "DestinationName": [{"value": "Gare St-Paul"}],
     "VehicleLocation": {"Longitude": 4.88, "Latitude": 45.77}, "Bearing": 225, "VehicleRef": {"value": "V1"},
     "OnwardCalls": {"OnwardCall": [{"StopPointRef": {"value": "ActIV:StopPoint:BP:30170:SYTRAL"}}]}}},
    # approche d'après le cap
    {"MonitoredVehicleJourney": {"LineRef": {"value": "ActIV:Line::C3:SYTRAL"}, "DestinationName": [{"value": "Gare Saint-Paul"}],
     "VehicleLocation": {"Longitude": 4.87, "Latitude": 45.765}, "Bearing": 230, "VehicleRef": {"value": "V2"}}},
    # s'éloigne (cap opposé)
    {"MonitoredVehicleJourney": {"LineRef": {"value": "ActIV:Line::C3:SYTRAL"}, "DestinationName": [{"value": "Gare Saint-Paul"}],
     "VehicleLocation": {"Longitude": 4.85, "Latitude": 45.755}, "Bearing": 240, "VehicleRef": {"value": "V3"}}},
    # autre direction
    {"MonitoredVehicleJourney": {"LineRef": {"value": "ActIV:Line::C3:SYTRAL"}, "DestinationName": [{"value": "Laurent Bonnevay"}],
     "VehicleLocation": {"Longitude": 4.87, "Latitude": 45.765}, "Bearing": 230, "VehicleRef": {"value": "V4"}}},
    # autre ligne
    {"MonitoredVehicleJourney": {"PublishedLineName": [{"value": "86"}], "DestinationName": [{"value": "La Doua"}],
     "VehicleLocation": {"Longitude": 4.865, "Latitude": 45.762}, "Bearing": 0, "VehicleRef": {"value": "V5"}}},
]}]}}}

VELOV = {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [4.83, 45.75]},
    "properties": {"number": 2010, "name": "Bellecour", "address": "Place Bellecour", "available_bikes": 7,
                   "available_bike_stands": 13, "bike_stands": 20, "status": "OPEN",
                   "total_stands": {"availabilities": {"electricalBikes": 3, "mechanicalBikes": 4}, "capacity": 20}}}]}

ALERTES = {"values": [{"ligne_com": "C3A", "ligne_cli": "C3", "titre": "Travaux Cordeliers", "message": "...",
                       "debut": "2020-01-01 00:00:00", "fin": "2099-01-01 00:00:00"}]}


@pytest.fixture
def api_mock(aioclient_mock):
    aioclient_mock.get(re.compile(re.escape(URL_PASSAGES) + ".*"), json=passages())
    aioclient_mock.get(re.compile(re.escape(URL_ARRETS) + ".*"), json={"values": [STOP]})
    aioclient_mock.get(re.compile(re.escape(URL_ALERTES[0]) + ".*"), json=ALERTES)
    aioclient_mock.get(re.compile(re.escape(URL_ALERTES[1]) + ".*"), status=403)
    aioclient_mock.get(re.compile(re.escape(URL_POSITIONS) + ".*"), json=SIRI)
    aioclient_mock.get(re.compile(re.escape(URL_VELOV.split("?")[0]) + ".*"), json=VELOV)
    return aioclient_mock


def test_parsers():
    v = parse_siri_vm(SIRI)
    assert [x["ligne"] for x in v] == ["C3", "C3", "C3", "C3", "86"]
    assert v[0]["prochains_arrets"] == ["30170"]
    assert v[0]["direction"] == "Gare St-Paul"
    s = parse_velov(VELOV["features"][0])
    assert (s["id"], s["velos"], s["places"], s["velos_electriques"]) == ("2010", 7, 13, 3)
    assert line_base("C3A") == "C3" and line_base("A") == "A" and line_base("JD123") == "JD123"


def test_approaching():
    vehicles = parse_siri_vm(SIRI)
    res = approaching_vehicles(vehicles, {}, [45.7605, 4.8597], "C3A", "Gare Saint-Paul", "30170")
    assert {v["id"] for v in res} == {"V1", "V2"}
    # V2 s'éloigne d'après sa position précédente -> exclu
    res = approaching_vehicles(vehicles, {"V2": [45.763, 4.865]}, [45.7605, 4.8597], "C3A", "Gare Saint-Paul", "30170")
    assert {v["id"] for v in res} == {"V1"}


async def test_full_flow(hass: HomeAssistant, api_mock):
    # 1. identifiants
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"username": "moi@example.com", "password": "secret"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    await hass.async_block_till_done()

    # 2. ajout d'un arrêt et de lignes
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "search"})
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"query": "vivier"})
    assert result["step_id"] == "stop"
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"stop_id": "30170"})
    assert result["step_id"] == "lines"
    opts = [o["value"] for o in result["data_schema"].schema["choices"].config["options"]]
    choice = next(o for o in opts if o.startswith("C3A") and "Saint-Paul" in o)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"choices": [choice]})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    # 3. ajout Vélo'v
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "velov_search"})
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"query": "bellecour"})
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"stations": ["2010"]})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    # 4. réglages carte
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "settings"})
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"positions_url": URL_POSITIONS, "map_bearing": 45})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert len(entry.options["tracks"]) == 1 and len(entry.options["velov"]) == 1

    states = {s.entity_id: s for s in hass.states.async_all("sensor")}
    print(list(states))
    dep = next(s for s in states.values() if s.attributes.get("type") == "depart")
    assert dep.state in ("1", "2")
    a = dep.attributes
    assert len(a["departs"]) == 2 and a["departs"][0]["temps_reel"] is True
    assert a["alertes"][0]["titre"] == "Travaux Cordeliers"
    assert a["carte_disponible"] is True and a["arret_position"] == [45.7605, 4.8597]
    assert a["carte_orientation"] == 45
    assert {v["id"] for v in a["vehicules"]} == {"V1", "V2"}
    vel = next(s for s in states.values() if s.attributes.get("type") == "velov")
    assert vel.state == "7" and vel.attributes["places"] == 13



async def test_card_served(hass: HomeAssistant, hass_client, api_mock):
    entry = MockConfigEntry(domain=DOMAIN, data={"username": "u", "password": "p"},
                            options={"tracks": [], "velov": []})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    client = await hass_client()
    r = await client.get("/tcl_lyon/tcl-departures-card.js")
    assert r.status == 200 and "tcl-departures-card" in await r.text()
    r = await client.get("/tcl_lyon/maplibre/maplibre-gl.js")
    assert r.status == 200
