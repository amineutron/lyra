"""Tests de la sequence power_on du serveur pylips-mcp (API simulee).

Regression 2026-08-12 : depuis la veille profonde, power_on envoyait le
Wake-on-LAN puis rendait la main ("attends 15-20s") sans jamais terminer
l'allumage ; et le chemin veille reseau repondait "TV allumee" sans
verifier l'etat reel. La nouvelle sequence est auto-suffisante et verifiee.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

SERVER_PATH = (Path(__file__).parent.parent.parent
               / "mcp-servers" / "pylips-mcp" / "server.py")

# Installation partielle (sans le MCP TV) : on saute au lieu d'echouer
pytestmark = pytest.mark.skipif(
    not SERVER_PATH.exists(),
    reason="mcp-servers/pylips-mcp absent de cette installation",
)


@pytest.fixture(scope="module")
def server_module():
    spec = importlib.util.spec_from_file_location("pylips_server", SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["pylips_server"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def controller(server_module):
    tv = server_module.PhilipsTVController(
        host="192.0.2.1", user="u", password="p", mac="00:11:22:33:44:55")
    tv._initialized = True  # skip init pylips reel
    return tv


def scripted_api(responses):
    """_api_call simule : rejoue une liste de reponses puis repete la derniere."""
    calls = []

    def fake(path, method="GET", body=None, **kwargs):
        calls.append((path, method, body))
        index = min(len(calls) - 1, len(responses) - 1)
        return responses[index]

    fake.calls = calls
    return fake


class TestPowerOn:
    def test_deja_allumee(self, controller):
        controller._api_call = scripted_api([{"powerstate": "On"}])
        assert controller.power_on() == "TV deja allumee"

    def test_veille_reseau_sequence_complete_et_verifiee(self, controller):
        # check=Standby -> key -> POST On -> confirm=On
        controller._api_call = scripted_api([
            {"powerstate": "Standby"},   # check initial
            {},                          # input/key Standby
            {},                          # POST powerstate On
            {"powerstate": "On"},        # confirmation
        ])
        assert controller.power_on() == "TV allumee"
        paths = [c[0] for c in controller._api_call.calls]
        assert paths == ["powerstate", "input/key", "powerstate", "powerstate"]
        # l'ordre toggle-puis-ordre-ferme est garanti
        assert controller._api_call.calls[2] == ("powerstate", "POST",
                                                 {"powerstate": "On"})

    def test_veille_profonde_wol_puis_api(self, controller):
        wol_sent = []
        controller._send_wol = lambda: wol_sent.append(True)
        controller._api_call = scripted_api([
            {"error": "timeout"},        # check initial: injoignable
            {"powerstate": "Standby"},   # reveil reseau apres WoL
            {},                          # input/key
            {},                          # POST On
            {"powerstate": "On"},        # confirmation
        ])
        result = controller.power_on()
        assert wol_sent, "le WoL doit etre envoye"
        assert result == "TV allumee (via Wake-on-LAN + API)"

    def test_veille_profonde_wol_reveil_deja_on(self, controller):
        controller._send_wol = lambda: None
        controller._api_call = scripted_api([
            {"error": "timeout"},
            {"powerstate": "On"},        # la TV s'est allumee toute seule
        ])
        assert controller.power_on() == "TV allumee (reveillee par Wake-on-LAN)"

    def test_wol_sans_reponse_erreur_claire(self, controller):
        controller._send_wol = lambda: None
        controller._wait_reachable = lambda deadline_s: None  # jamais joignable
        controller._api_call = scripted_api([{"error": "timeout"}])
        with pytest.raises(RuntimeError, match="coupee du secteur"):
            controller.power_on()

    def test_sequence_sans_effet_erreur_honnete(self, controller):
        # Tout repond mais la TV reste en veille -> on ne ment pas
        controller._confirm_on = lambda deadline_s: "Standby"
        controller._api_call = scripted_api([
            {"powerstate": "Standby"}, {}, {},
        ])
        with pytest.raises(RuntimeError, match="reste en etat 'Standby'"):
            controller.power_on()

    def test_pas_de_mac_erreur_claire(self, server_module):
        tv = server_module.PhilipsTVController(host="192.0.2.1", user="u",
                                               password="p", mac="")
        tv._initialized = True
        tv._api_call = scripted_api([{"error": "timeout"}])
        with pytest.raises(RuntimeError, match="aucune MAC"):
            tv.power_on()


class TestHelpers:
    def test_wait_reachable_retourne_l_etat(self, controller):
        controller._api_call = scripted_api([{"powerstate": "Standby"}])
        state = controller._wait_reachable(deadline_s=1.0)
        assert state == {"powerstate": "Standby"}

    def test_wait_reachable_timeout(self, controller):
        controller._api_call = scripted_api([{"error": "x"}])
        assert controller._wait_reachable(deadline_s=0.1) is None

    def test_confirm_on_immediat(self, controller):
        controller._api_call = scripted_api([{"powerstate": "On"}])
        assert controller._confirm_on(deadline_s=1.0) == "On"

    def test_confirm_on_rapporte_le_dernier_etat(self, controller):
        controller._api_call = scripted_api([{"powerstate": "StandbyKeep"}])
        assert controller._confirm_on(deadline_s=0.1) == "StandbyKeep"
