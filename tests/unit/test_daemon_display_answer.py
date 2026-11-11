"""Reponses aux clics du display et etat reel des confirmations."""

import socket
import threading
import time
from types import SimpleNamespace

import pytest

from lyra.daemon.display import (
    build_display,
    parse_slider_answer,
    translate_confirm_answer,
)
from lyra.daemon.display_state import fetch_display_state
from lyra.daemon.protocol import LineChannel
from lyra.daemon.remote_ui import RemoteUI

VMS = {"vms": [{"name": "web", "state": "running"}, {"name": "db", "state": "stopped"}]}
TV_DISPLAY = build_display("tv.volume_set", {"level": 30}, {"volume": 20, "muted": False})
VM_DISPLAY = build_display("fedora.vm_start", {"vm_name": "web"}, VMS)
CHOICES = build_display("choices", {"choices": ["a", "b"]}, None)


class TestTranslate:
    @pytest.mark.parametrize(("display", "tool", "args", "danger", "raw", "answer", "eff"), [
        # clic sur la cible d'une action non dangereuse -> confirme
        (VM_DISPLAY, "fedora.vm_start", {"vm_name": "web"}, False, "web", "o", None),
        # autre element : pas de changement de cible ici -> refus
        (VM_DISPLAY, "fedora.vm_start", {"vm_name": "web"}, False, "db", "n", None),
        # action dangereuse : jamais de confirmation par clic catalogue
        (VM_DISPLAY, "fedora.vm_stop", {"vm_name": "web"}, True, "web", "n", None),
        # id invente : reponse texte classique (donc non confirmee ensuite)
        (VM_DISPLAY, "fedora.vm_start", {"vm_name": "web"}, False, "ghost", "ghost", None),
        # reponses classiques inchangees
        (VM_DISPLAY, "fedora.vm_start", {"vm_name": "web"}, False, "O", "O", None),
        (VM_DISPLAY, "fedora.vm_start", {"vm_name": "web"}, False, "", "", None),
        (VM_DISPLAY, "fedora.vm_start", {"vm_name": "web"}, False, "m", "m", None),
        # curseur valide : copie des arguments avec le niveau
        (TV_DISPLAY, "tv.volume_set", {"level": 30}, False, "volume=45", "o", {"level": 45}),
        (TV_DISPLAY, "tv.volume_set", {"level": 30}, False, "volume=0", "o", {"level": 0}),
        (TV_DISPLAY, "tv.volume_set", {"level": 30}, False, "volume=60", "o", {"level": 60}),
        # hors plage / forme invalide / id inconnu -> refus
        (TV_DISPLAY, "tv.volume_set", {"level": 30}, False, "volume=61", "n", None),
        (TV_DISPLAY, "tv.volume_set", {"level": 30}, False, "volume=-1", "n", None),
        (TV_DISPLAY, "tv.volume_set", {"level": 30}, False, "volume=999999", "n", None),
        (TV_DISPLAY, "tv.volume_set", {"level": 30}, False, "other=10", "n", None),
        # curseur sur un outil qui n'a pas d'argument absolu ou dangereux -> refus
        (TV_DISPLAY, "tv.volume_up", {}, False, "volume=10", "n", None),
        (TV_DISPLAY, "tv.volume_set", {"level": 30}, True, "volume=10", "n", None),
        # choix : jamais une confirmation
        (CHOICES, "choices", {}, False, "1", "n", None),
        # sans display : brut
        (None, "catt.cast_stop", {}, False, "o", "o", None),
    ])
    def test_table(self, display, tool, args, danger, raw, answer, eff):
        got, effective = translate_confirm_answer(display, raw, tool, args, danger)
        assert got == answer
        assert effective == (eff if eff is not None else args)

    def test_arguments_d_origine_non_mutes(self):
        args = {"level": 30}
        translate_confirm_answer(TV_DISPLAY, "volume=45", "tv.volume_set", args, False)
        assert args == {"level": 30}

    @pytest.mark.parametrize("raw", ["volume=4.5", "volume=1e1", "volume= 5", "volume=+5",
                                     "volume=5; rm", "volume=", "=5"])
    def test_curseur_forme_stricte(self, raw):
        assert parse_slider_answer(TV_DISPLAY, raw) is None

    def test_parse_slider_ok(self):
        assert parse_slider_answer(TV_DISPLAY, "volume=12") == ("volume", 12)


def _confirm_with(answer, tool, args, danger, state_provider=None):
    server_sock, client_sock = socket.socketpair()
    server, client = LineChannel(server_sock), LineChannel(client_sock)
    sent = {}

    def responder():
        sent.update(client.recv(timeout=5))
        client.send({"type": "answer", "value": answer})
    thread = threading.Thread(target=responder)
    thread.start()
    try:
        rui = RemoteUI(server, state_provider=state_provider)
        out = rui.ask_confirm(tool, args, "prompt", danger)
        thread.join(timeout=5)
    finally:
        server.close()
        client.close()
    return out, sent


class TestAskConfirm:
    def test_clic_valide_contre_le_display_emis(self):
        provider = lambda t, a: VMS  # noqa: E731
        (answer, _), sent = _confirm_with("web", "fedora.vm_start", {"vm_name": "web"},
                                          False, provider)
        assert answer == "o"
        assert sent["payload"]["display"]["items"][0]["state"] == "running"

    def test_id_d_un_autre_display_refuse(self):
        # "db" n'est pas propose : pas de provider, display = cible seule
        (answer, _), _ = _confirm_with("db", "fedora.vm_start", {"vm_name": "web"}, False)
        assert answer == "db"          # texte brut, non confirme par la logique O/n

    def test_curseur_modifie_les_arguments(self):
        (answer, eff), _ = _confirm_with("volume=33", "tv.volume_set", {"level": 5}, False)
        assert (answer, eff) == ("o", {"level": 33})

    def test_confirm_action_refuse_curseur(self):
        server_sock, client_sock = socket.socketpair()
        server, client = LineChannel(server_sock), LineChannel(client_sock)

        def responder():
            client.recv(timeout=5)
            client.send({"type": "answer", "value": "volume=33"})
        thread = threading.Thread(target=responder)
        thread.start()
        try:
            assert RemoteUI(server).confirm_action("tv.volume_set", {"level": 5}) is False
            thread.join(timeout=5)
        finally:
            server.close()
            client.close()

    def test_confirm_action_clic_cible(self):
        server_sock, client_sock = socket.socketpair()
        server, client = LineChannel(server_sock), LineChannel(client_sock)

        def responder():
            client.recv(timeout=5)
            client.send({"type": "answer", "value": "web"})
        thread = threading.Thread(target=responder)
        thread.start()
        try:
            rui = RemoteUI(server)
            assert rui.confirm_action("fedora.vm_start", {"vm_name": "web"},
                                      danger=False) is True
            thread.join(timeout=5)
        finally:
            server.close()
            client.close()

    def test_provider_qui_leve_ne_bloque_pas(self):
        def boom(*_a):
            raise RuntimeError("down")
        (answer, _), sent = _confirm_with("o", "tv.volume_set", {"level": 5}, False, boom)
        assert answer == "o" and "display" in sent["payload"]


def hestia(content_by_tool, delay=0.0):
    def execute(tool, args, context=None):
        time.sleep(delay)
        content = content_by_tool[tool]
        if isinstance(content, Exception):
            raise content
        return SimpleNamespace(success=True, content=content)
    return SimpleNamespace(execute=execute)


class TestFetchState:
    def test_vm_running(self):
        h = hestia({"fedora.vm_status": "Status: running\nIP: 192.0.2.5"})
        assert fetch_display_state(h, "fedora.vm_stop", {"vm_name": "web"}) == \
            {"vms": [{"name": "web", "state": "running"}]}

    def test_vm_stopped(self):
        h = hestia({"fedora.vm_status": "Status: shut off"})
        state = fetch_display_state(h, "vm_start", {"vm_name": "web"})
        assert state["vms"][0]["state"] == "stopped"

    @pytest.mark.parametrize(("content", "expected"), [
        ('{"volume": 17, "muted": true}', {"volume": 17, "muted": True}),
        ("Volume: 22\nMuted: false", {"volume": 22, "muted": False}),
        ("rien d'utile", None),
    ])
    def test_tv(self, content, expected):
        h = hestia({"tv.get_state": content})
        assert fetch_display_state(h, "tv.volume_set", {"level": 5}) == expected

    def test_tv_hors_volume_pas_de_lecture(self):
        assert fetch_display_state(hestia({}), "tv.power_on", {}) is None

    def test_hue_groupes(self):
        h = hestia({"hue.get_all_groups": '{"1": {"name": "Salon"}}'})
        state = fetch_display_state(h, "hue.turn_off_group", {"group_id": "1"})
        assert build_display("hue.turn_off_group", {"group_id": "1"}, state)["items"][0] == \
            {"id": "1", "label": "Salon", "selected": True}

    def test_echec_retombe_sur_none(self):
        h = hestia({"tv.get_state": RuntimeError("down")})
        assert fetch_display_state(h, "tv.volume_set", {}) is None

    def test_lenteur_retombe_sur_none_vite(self):
        h = hestia({"tv.get_state": '{"volume": 3}'}, delay=1.0)
        start = time.monotonic()
        assert fetch_display_state(h, "tv.volume_set", {}, timeout=0.05) is None
        assert time.monotonic() - start < 0.6

    @pytest.mark.parametrize("hst", [None])
    def test_sans_hestia(self, hst):
        assert fetch_display_state(hst, "vm_stop", {"vm_name": "x"}) is None
