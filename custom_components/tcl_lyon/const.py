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

URL_ALERTES = f"{BASE_URL}/tcl_sytral.tclalertetrafic_2/all.json"
URL_VELOV = f"{BASE_URL}/jcd_jcdecaux.jcdvelov/all.json"

ALERTES_INTERVAL = timedelta(minutes=5)
VELOV_INTERVAL = timedelta(seconds=60)
