"""Tests de lyra/daemon/display.py : description declarative pour la capsule."""

import json
import socket
import threading

import pytest

from lyra.daemon import remote_ui
from lyra.daemon.display import build_display, resolve_display_answer
from lyra.daemon.protocol import LineChannel
from lyra.daemon.remote_ui import RemoteUI, build_confirm_payload

VMS_STATE = {"vms": [{"name": "web", "state": "running"},
                     {"name": "db", "state": "shut off"}]}
GROUPS_STATE = {"groups": {"1": {"name": "Salon", "state": {"any_on": True}},
                           "2": {"name": "Chambre", "on": False}}}


def ids(display):
    return [item["id"] for item in display["items"]]


# ---------------------------------------------------------------------------
# build_display
# ---------------------------------------------------------------------------

class TestBuildDisplay:
    @pytest.mark.parametrize("tool", [
        "tv.volume_set", "tv.volume_up", "tv.volume_down", "tv.mute",
    ])
    def test_tv_volume_avec_slider(self, tool):
        display = build_display(tool, {"level": 20}, {"volume": 12, "muted": False})
        assert display["kind"] == "tv"
        assert display["pin"] is False
        assert display["controls"] == [
            {"type": "slider", "id": "volume", "min": 0, "max": 60, "value": 12}]
        assert display["items"][0]["value"] == 12
        assert {"id": "mute", "label": "Muet", "state": "non"} in display["items"]

    @pytest.mark.parametrize(("arguments", "state", "expected"), [
        ({"level": 20}, None, 20),        # pas de state : cible demandee
        ({"level": 20}, {"volume": 7}, 7),  # state prime
        ({"level": 999}, None, 60),       # borne haute
        ({"level": -5}, None, 0),         # borne basse
        ({}, None, 0),
        ({"level": "abc"}, {"volume": "x"}, 0),
        ({"level": True}, None, 0),
    ])
    def test_tv_valeur_courante_et_bornes(self, arguments, state, expected):
        display = build_display("tv.volume_set", arguments, state)
        assert display["controls"][0]["value"] == expected

    @pytest.mark.parametrize("tool", ["tv.power_on", "tv.launch_app", "tv.get_state"])
    def test_tv_sans_volume_pas_de_display(self, tool):
        assert build_display(tool, {}, {"volume": 10}) is None

    @pytest.mark.parametrize("tool", ["fedora.vm_stop", "vm_stop", "fedora.vm_start"])
    def test_vms_cible_selectionnee(self, tool):
        display = build_display(tool, {"vm_name": "db"}, VMS_STATE)
        assert display["kind"] == "vms"
        assert ids(display) == ["web", "db"]
        assert [i.get("selected", False) for i in display["items"]] == [False, True]
        assert display["items"][1]["state"] == "shut off"
        assert "controls" not in display

    @pytest.mark.parametrize(("arguments", "state", "expected_ids"), [
        ({"vm_name": "web"}, {"vms": {"web": "running", "db": "off"}}, ["web", "db"]),
        ({"vm_name": "web"}, {"vms": ["web", "db"]}, ["web", "db"]),
        ({"vm_name": "web"}, None, ["web"]),                    # sans state : la cible seule
        ({"source_vm": "web"}, {}, ["web"]),
        ({}, VMS_STATE, ["web", "db"]),                         # sans cible : rien de selectionne
        ({}, None, None),                                       # rien a montrer
        ({"vm_name": 12}, {"vms": "n'importe quoi"}, None),
    ])
    def test_vms_formats_de_state(self, arguments, state, expected_ids):
        display = build_display("vm_stop", arguments, state)
        assert (None if display is None else ids(display)) == expected_ids

    def test_vms_sans_cible_aucun_selected(self):
        display = build_display("vm_status", {}, VMS_STATE)
        assert not any(i.get("selected") for i in display["items"])

    def test_lumieres_groupes(self):
        display = build_display("hue.set_group_brightness",
                                {"group_id": 2, "brightness": 100}, GROUPS_STATE)
        assert display["kind"] == "lights"
        assert ids(display) == ["1", "2"]
        assert [i["state"] for i in display["items"]] == ["on", "off"]
        assert [i.get("selected", False) for i in display["items"]] == [False, True]

    def test_lumieres_individuelles(self):
        state = {"lights": [{"id": 5, "name": "Bureau", "on": True}]}
        display = build_display("hue_set_brightness", {"light_id": 5}, state)
        assert display["items"] == [
            {"id": "5", "label": "Bureau", "state": "on", "selected": True}]

    @pytest.mark.parametrize("tool", ["hue.hue_beat_status", "hue.get_all_lights"])
    def test_lumieres_sans_liste_pas_de_display(self, tool):
        assert build_display(tool, {}, None) is None

    def test_choices_ids_numerotes(self):
        display = build_display("choices", {"title": "Quelle VM ?",
                                            "choices": ["web", "db"]}, None)
        assert display["kind"] == "choices" and display["title"] == "Quelle VM ?"
        assert display["items"] == [{"id": "1", "label": "web"},
                                    {"id": "2", "label": "db"}]

    def test_choices_ids_fournis(self):
        raw = [{"id": "a", "label": "Alpha", "selected": True, "value": 3},
               {"id": "a", "label": "doublon"}]
        display = build_display("choices", {"choices": raw}, None)
        assert display["items"] == [
            {"id": "a", "label": "Alpha", "value": 3, "selected": True}]
        assert display["title"] == "Choix"

    def test_sessions(self):
        display = build_display("sessions", {"sessions": [
            {"id": "s1", "label": "Build", "state": "running"}]}, None)
        assert display["kind"] == "sessions"
        assert display["items"][0]["state"] == "running"

    @pytest.mark.parametrize(("tool", "arguments", "state"), [
        ("denon.volume_set", {"level": 40}, {"volume": 40}),
        ("catt.cast_stop", {}, None),
        ("backup_create", {}, None),
        ("", {}, None),
        ("choices", {"choices": []}, None),
        ("choices", {"choices": "pas une liste"}, None),
        (None, {}, None),
    ])
    def test_inconnu_ou_vide_donne_none(self, tool, arguments, state):
        assert build_display(tool, arguments, state) is None

    def test_arguments_et_state_non_dict_toleres(self):
        assert build_display("tv.volume_set", None, None)["kind"] == "tv"
        assert build_display("vm_stop", "x", ["y"]) is None

    def test_sortie_json_serialisable_et_bornee(self):
        many = {"vms": [{"name": f"vm{i}", "state": "on"} for i in range(500)]}
        display = build_display("vm_stop", {"vm_name": "vm1"}, many)
        assert len(display["items"]) == 50
        assert json.loads(json.dumps(display)) == display

    def test_texte_nettoye(self):
        state = {"vms": [{"name": "a\x1b[31m\nb" + "x" * 500, "state": "ok\x00"}]}
        item = build_display("vm_stop", {}, state)["items"][0]
        assert "\x1b" not in item["id"] and "\n" not in item["id"]
        assert len(item["id"]) <= 64 and len(item["label"]) <= 80
        assert "\x00" not in item["state"]

    @pytest.mark.parametrize("name", ["o", "oui", "N", "m", "yes", ""])
    def test_ids_reserves_de_confirmation_jamais_proposes(self, name):
        display = build_display("vm_stop", {}, {"vms": [name, "ok"]})
        assert ids(display) == ["ok"]


# ---------------------------------------------------------------------------
# resolve_display_answer
# ---------------------------------------------------------------------------

class TestResolveDisplayAnswer:
    DISPLAY = build_display("vm_stop", {"vm_name": "web"}, VMS_STATE)

    @pytest.mark.parametrize(("value", "expected"), [
        ("web", "web"),
        ("db", "db"),
        ("inconnue", None),
        ("WEB", None),                        # exact, pas de normalisation
        (" web", None),
        ("web ", None),
        ("", None),
        ("web; rm -rf /", None),              # injection
        ("x; rm -rf ~", None),
        ("$(reboot)", None),
        ("web\nrm -rf /", None),
        ("../../etc/passwd", None),
        ("db' OR '1'='1", None),
        (None, None),
        (1, None),
        (["web"], None),
        ({"id": "web"}, None),
    ])
    def test_validation_contre_les_ids(self, value, expected):
        assert resolve_display_answer(self.DISPLAY, value) == expected

    @pytest.mark.parametrize("display", [
        None, {}, {"items": None}, {"items": "web"}, {"items": [None, 3, {"id": 7}]},
        "web", [],
    ])
    def test_display_invalide(self, display):
        assert resolve_display_answer(display, "web") is None

    def test_rend_l_id_du_display_pas_la_valeur_cliente(self):
        class Spoof(str):
            def __eq__(self, other):
                return True
            __hash__ = str.__hash__

        out = resolve_display_answer(self.DISPLAY, Spoof("web"))
        # le resultat vient du display, pas de l'objet fourni par l'appelant
        assert type(out) is str


# ---------------------------------------------------------------------------
# Emission dans le ask confirm
# ---------------------------------------------------------------------------

class TestConfirmEmission:
    def test_payload_avec_display(self):
        payload = build_confirm_payload("fedora.vm_stop", {"vm_name": "web"}, True)
        assert payload["tool"] == "fedora.vm_stop" and payload["danger"] is True
        assert payload["display"]["kind"] == "vms"

    def test_payload_sans_display_reste_inchange(self):
        payload = build_confirm_payload("catt.cast_stop", {}, False)
        assert payload == {"tool": "catt.cast_stop", "arguments": {}, "danger": False}

    def test_echec_de_build_display_ne_bloque_pas(self, monkeypatch):
        def boom(*_a, **_k):
            raise RuntimeError("bug")
        monkeypatch.setattr(remote_ui, "build_display", boom)
        payload = build_confirm_payload("vm_stop", {"vm_name": "web"}, True)
        assert "display" not in payload and payload["tool"] == "vm_stop"

    def test_ask_confirm_envoye_au_client_avec_display(self):
        server_sock, client_sock = socket.socketpair()
        server, client = LineChannel(server_sock), LineChannel(client_sock)
        received = {}

        def responder():
            received.update(client.recv(timeout=5))
            client.send({"type": "answer", "value": "non"})
        thread = threading.Thread(target=responder)
        thread.start()
        try:
            result = RemoteUI(server).confirm_action(
                "tv.volume_set", {"level": 30}, danger=False)
            thread.join(timeout=5)
        finally:
            server.close()
            client.close()
        assert result is False
        assert received["type"] == "ask" and received["kind"] == "confirm"
        assert received["payload"]["display"]["kind"] == "tv"
        assert received["payload"]["arguments"] == {"level": 30}
