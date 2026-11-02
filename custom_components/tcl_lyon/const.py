"""Constantes de l'intégration TCL Lyon."""
from datetime import timedelta

DOMAIN = "tcl_lyon"

CONF_TRACKS = "tracks"
CONF_STOP_ID = "stop_id"
CONF_STOP_NAME = "stop_name"
CONF_LIGNE = "ligne"
CONF_DIRECTION = "direction"  # "" = toutes les directions

BASE_URL = "https://download.data.grandlyon.com/ws/rdata"
URL_PASSAGES = f"{BASE_URL}/tcl_sytral.tclpassagearret/all.json"
URL_ARRETS = f"{BASE_URL}/tcl_sytral.tclarret/all.json"

SCAN_INTERVAL = timedelta(seconds=20)
MAX_DEPARTURES = 6

CONF_VELOV = "velov"
CONF_VELOV_ID = "id"
CONF_VELOV_NAME = "name"

URL_ALERTES = [
    f"{BASE_URL}/tcl_sytral.tclalertetrafic_2/all.json",
    f"{BASE_URL}/jd_juniordirect.jdalertetrafic_2/all.json",  # lignes scolaires (Junior Direct)
]
URL_VELOV = (
    "https://data.grandlyon.com/geoserver/metropole-de-lyon/ows?SERVICE=WFS&VERSION=2.0.0"
    "&request=GetFeature&typename=metropole-de-lyon:jcd_jcdecaux.jcdvelov"
    "&outputFormat=application/json&SRSNAME=EPSG:4171&sortBy=gid"
)
URL_POSITIONS = "https://data.grandlyon.com/siri-lite/2.0/vehicle-monitoring.json"

ALERTES_INTERVAL = timedelta(minutes=5)
VELOV_INTERVAL = timedelta(seconds=60)

CONF_POSITIONS_URL = "positions_url"
CONF_MAP_BEARING = "map_bearing"
MAX_VEHICLES = 8
MAX_VEHICLE_DISTANCE_M = 12000
