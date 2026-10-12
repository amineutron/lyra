"""Test de fumee du demon : ses verifications (pures) et un passage complet sur un faux demon."""
from __future__ import annotations

import importlib.util
import socketserver
import threading
from pathlib import Path

import pytest

from lyra.daemon.protocol import LineChannel

_spec = importlib.util.spec_from_file_location("smoke_daemon", Path(__file__).resolve().parents[2] / "scripts" / "smoke_daemon.py")
smoke = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(smoke)

GOOD = {"type": "analysis", "found": True, "tool": "tv.power_on", "performance": True, "dangerous": False}
REFUSED = [{"type": "error", "text": "outil non autorise sans presence humaine"}, {"type": "result", "exit_code": 1}]


@pytest.mark.parametrize("message,ok", [
    (GOOD, True),
    ({**GOOD, "found": False}, False),
    ({**GOOD, "tool": "hue.turn_off_group"}, False),
    ({**GOOD, "dangerous": True}, False),
    ({"type": "error", "text": "type de message inconnu"}, False),      # demon pas encore redemarre
])
def test_verification_de_l_analyse(message, ok):
    assert (smoke.check_analysis(message) == "") is ok


@pytest.mark.parametrize("replies,ok", [
    (REFUSED, True),
    ([{"type": "result", "exit_code": 0}], False),                                        # accepte : grave
    ([{"type": "ask", "kind": "confirm"}], False),                                        # question sans humain
    ([{"type": "output", "kind": "tool_result", "success": True}, {"type": "result", "exit_code": 1}], False),
    ([{"type": "error", "text": "outil inconnu: fedora.vm_status"}, {"type": "result", "exit_code": 1}], False),   # refus non prouve
    ([], False),
])
def test_verification_du_refus_sans_humain(replies, ok):
    assert (smoke.check_refusal(replies) == "") is ok


def test_etat_du_demon():
    assert smoke.check_ready({"type": "ready", "status": "ready"}) == ""
    assert "loading" in smoke.check_ready({"type": "ready", "status": "loading"})


def _serve(tmp_path, accept_unattended: bool):
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            ch = LineChannel(self.request)
            try:
                while True:
                    m = ch.recv(2)
                    if m["type"] == "hello":
                        ch.send({"type": "ready", "status": "ready", "uptime": 1.0})
                    elif m["type"] == "ping":
                        ch.send({"type": "pong"})
                    elif m["type"] == "health":
                        ch.send({"type": "health", "data": {}})
                    elif m["type"] == "analyze":
                        ch.send(GOOD)
                    elif m["type"] == "tool":
                        for reply in ([{"type": "result", "exit_code": 0}] if accept_unattended else REFUSED):
                            ch.send(reply)
            except Exception:
                pass

    path = tmp_path / "s.sock"
    server = socketserver.ThreadingUnixStreamServer(str(path), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return path, server


def test_passage_complet_sur_un_demon_sain(tmp_path):
    path, server = _serve(tmp_path, accept_unattended=False)
    try:
        assert smoke.run(path) == [("hello", ""), ("ping", ""), ("health", ""), ("analyze", ""), ("unattended", "")]
    finally:
        server.shutdown()
        server.server_close()


def test_un_demon_qui_accepte_tout_sans_humain_est_signale(tmp_path):
    path, server = _serve(tmp_path, accept_unattended=True)
    try:
        assert dict(smoke.run(path))["unattended"] != ""
    finally:
        server.shutdown()
        server.server_close()


def test_demon_absent(tmp_path):
    assert smoke.run(tmp_path / "absent.sock")[0][0] == "connexion"
