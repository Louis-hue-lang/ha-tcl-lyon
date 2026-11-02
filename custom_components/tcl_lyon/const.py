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

SCAN_INTERVAL = timedelta(seconds=60)
MAX_DEPARTURES = 6
