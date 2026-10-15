"""Scenario de bout en bout d'une automatisation neutroncore (roadmap : « phrase envoyee a Lyra »).

1. A l'ecriture de l'automatisation : le client demande l'ANALYSE de la phrase.
2. L'utilisateur valide l'outil et les arguments resolus (hors de ce test).
3. A chaque declenchement : le client rejoue l'appel resolu par la route "tool",
   en mode sans presence humaine.

Vrai socket, vraies regles, vraies constantes de securite ; seule l'execution
MCP est simulee (aucun appareil n'est touche).
"""
from __future__ import annotations

import socket
import threading
import time
from types import SimpleNamespace as N
from unittest.mock import Mock

import pytest

from lyra.daemon import state as daemon_state
from lyra.daemon.protocol import LineChannel
from lyra.daemon.server import LyraDaemon, _ConnectionHandler, _Server

CATALOGUE = ("tv.power_on", "tv.launch_app", "hue.activate_scene_by_name", "hue.turn_off_group",
             "denon.volume_set", "fedora.vm_stop", "fedora.vm_destroy", "fedora.vm_list")


@pytest.fixture
def lyra(tmp_path):
    d = LyraDaemon.__new__(LyraDaemon)
    d.started_at = time.time()
    d.status = daemon_state.READY
    d._init_done = threading.Event()
    d._init_done.set()
    d._init_error = [None]
    d._busy = threading.Lock()
    d._busy_with = ""
    d._stop = threading.Event()
    v2 = Mock()
    v2._hestia.get_available_tools.return_value = [{"name": n} for n in CATALOGUE]
    v2.execute_action.side_effect = lambda name, arguments, **_k: N(executed=True, error=None, response=f"{name} ok")
    d.pipeline = N(_pipeline_v2=v2)
    path = tmp_path / "lyra-e2e.sock"
    server = _Server(str(path), _ConnectionHandler)
    server.daemon = d
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def call(message):
        """Envoie un message et rend tous les messages recus jusqu'a la fin de l'echange."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect(str(path))
        c = LineChannel(sock)
        c.send({"type": "hello", "session": "automation", "client": "api"})
        c.recv(timeout=5)
        c.send(message)
        out = []
        while True:
            m = c.recv(timeout=5)
            out.append(m)
            if m["type"] in ("analysis", "result") or (m["type"] == "error" and message["type"] == "analyze"):
                break
        c.close()
        return out
    try:
        yield call, v2
    finally:
        d._stop.set()
        server.shutdown()
        server.server_close()
        thread.join(5)


def _resoudre(call, phrase):
    return call({"type": "analyze", "text": phrase})[-1]


def _rejouer(call, analyse):
    return call({"type": "tool", "name": analyse["tool"], "arguments": analyse["arguments"],
                 "options": {"unattended": True}})


@pytest.mark.parametrize("phrase,tool,arguments", [
    ("allume la télé", "tv.power_on", {}),
    ("mets la scène soirée", "hue.activate_scene_by_name", {"scene_name": "soiree"}),
    ("monte le son de l'ampli à 40", "denon.volume_set", {"level": 40}),
    ("lance netflix sur la télé", "tv.launch_app", {"app": "netflix"}),
])
def test_phrase_resolue_a_l_edition_puis_rejouee_sans_humain(lyra, phrase, tool, arguments):
    call, v2 = lyra
    analyse = _resoudre(call, phrase)
    assert analyse["found"] and analyse["performance"] and (analyse["tool"], analyse["arguments"]) == (tool, arguments)
    v2.execute_action.assert_not_called()             # l'analyse n'a rien execute
    for _ in range(3):                                # trois declenchements : meme appel, sans modele
        recus = _rejouer(call, analyse)
        assert recus[-1] == {"type": "result", "exit_code": 0, "executed": True}
        assert recus[0]["kind"] == "tool_result" and recus[0]["success"] is True
    assert [c.args for c in v2.execute_action.call_args_list] == [(tool, arguments)] * 3


def test_action_sensible_resolue_mais_jamais_executee_sans_humain(lyra):
    call, v2 = lyra
    analyse = _resoudre(call, "arrête la vm preprod-01")
    assert analyse["found"] and analyse["dangerous"] and not analyse["performance"]
    recus = _rejouer(call, analyse)
    assert [m["type"] for m in recus] == ["error", "result"] and recus[-1]["exit_code"] == 1
    assert not any(m["type"] == "ask" for m in recus)  # pas de question a laquelle personne ne repondrait
    v2.execute_action.assert_not_called()


def test_phrase_non_reconnue_rien_a_rejouer(lyra):
    call, v2 = lyra
    analyse = _resoudre(call, "raconte-moi une histoire")
    assert analyse["found"] is False and analyse["tool"] == ""
    v2.execute_action.assert_not_called()


def test_un_appel_force_a_la_main_vers_un_outil_interdit_est_refuse(lyra):
    """Meme si le client stocke un appel qu'aucune analyse n'aurait autorise (fichier edite),
    le demon refuse : la garantie est portee ici, pas chez le client."""
    call, v2 = lyra
    for name in ("fedora.vm_destroy", "fedora.vm_list", "outil.inexistant"):
        recus = call({"type": "tool", "name": name, "arguments": {}, "options": {"unattended": True, "confirmed": True}})
        assert recus[-1]["exit_code"] == 1
    v2.execute_action.assert_not_called()
