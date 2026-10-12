"""Demon sur un VRAI socket UNIX temporaire : aiguillage des messages de bout en bout.

Le serveur de socket et son gestionnaire de connexion sont les vrais ; seul le
pipeline (modeles, serveurs MCP) est remplace. Aucun appareil, aucun Ollama.
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


@pytest.fixture
def daemon_socket(tmp_path):
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
    v2._hestia.get_available_tools.return_value = [{"name": n} for n in ("tv.power_on", "fedora.vm_stop", "fedora.vm_list")]
    v2.execute_action.return_value = N(executed=True, error=None, response="TV allumee")
    d.pipeline = N(_pipeline_v2=v2)
    path = tmp_path / "lyra-test.sock"
    server = _Server(str(path), _ConnectionHandler)
    server.daemon = d
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield path, d, v2
    finally:
        d._stop.set()
        server.shutdown()
        server.server_close()
        thread.join(5)


def _client(path) -> LineChannel:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(5)
    sock.connect(str(path))
    return LineChannel(sock)


def test_hello_ping_puis_analyse_sur_la_meme_connexion(daemon_socket):
    path, _, v2 = daemon_socket
    c = _client(path)
    c.send({"type": "hello", "session": "automation", "client": "api"})
    assert c.recv(timeout=5)["type"] == "ready"
    c.send({"type": "ping"})
    assert c.recv(timeout=5) == {"type": "pong"}
    c.send({"type": "analyze", "text": "allume la télé"})
    a = c.recv(timeout=5)
    assert a["type"] == "analysis" and a["tool"] == "tv.power_on" and a["performance"] is True
    c.send({"type": "analyze", "text": ""})
    assert c.recv(timeout=5)["type"] == "error"
    c.send({"type": "ping"})                         # la connexion survit a une erreur
    assert c.recv(timeout=5) == {"type": "pong"}
    v2.execute_action.assert_not_called()
    c.close()


def test_analyse_et_requete_longue_en_parallele(daemon_socket):
    """Un autre client tient le demon occupe : l'analyse repond quand meme, tout de suite."""
    path, d, _ = daemon_socket
    assert d._busy.acquire(blocking=False)           # simule une requete en cours
    try:
        c = _client(path)
        t0 = time.time()
        c.send({"type": "analyze", "text": "éteins les lumières"})
        a = c.recv(timeout=5)
        assert a["type"] == "analysis" and time.time() - t0 < 2
        c.close()
    finally:
        d._busy.release()


def test_deux_clients_simultanes(daemon_socket):
    path, _, _ = daemon_socket
    results = []

    def worker(phrase):
        c = _client(path)
        c.send({"type": "analyze", "text": phrase})
        results.append(c.recv(timeout=5)["tool"])
        c.close()
    threads = [threading.Thread(target=worker, args=(p,)) for p in ("allume la télé", "éteins les lumières") * 4]
    [t.start() for t in threads]
    [t.join(5) for t in threads]
    assert sorted(results) == ["hue.turn_off_group"] * 4 + ["tv.power_on"] * 4


def test_type_de_message_inconnu(daemon_socket):
    path, _, _ = daemon_socket
    c = _client(path)
    c.send({"type": "analyse"})                      # faute de frappe d'un client
    assert c.recv(timeout=5) == {"type": "error", "text": "type de message inconnu: analyse"}
    c.close()


def test_options_mal_formees_la_connexion_survit(daemon_socket):
    """Des options qui ne sont pas un objet valent « aucune option » : ni plantage, ni passe-droit."""
    path, _, v2 = daemon_socket
    c = _client(path)
    c.send({"type": "hello", "session": "automation", "client": "api"})
    assert c.recv(timeout=5)["type"] == "ready"
    c.send({"type": "tool", "name": "tv.power_on", "arguments": {}, "options": ["unattended"]})
    replies = []
    while not replies or replies[-1]["type"] != "result":
        replies.append(c.recv(timeout=5))
    assert replies[-1]["exit_code"] == 0
    c.send({"type": "ping"})
    assert c.recv(timeout=5) == {"type": "pong"}
    c.close()
