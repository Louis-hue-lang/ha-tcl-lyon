from unittest.mock import patch

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def fake_frontend():
    """Le paquet hass_frontend (interface web) n'est pas installé dans l'environnement de test."""
    async def _setup(hass, config):
        return True

    with patch("homeassistant.components.frontend.async_setup", _setup), patch(
        "custom_components.tcl_lyon.add_extra_js_url"
    ) as add_js:
        yield add_js
