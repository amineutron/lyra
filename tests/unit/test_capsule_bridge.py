"""Traduction demon -> capsule et clic -> reponse (quickshell/lyra-capsule/bridge)."""
import importlib.util
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[2] / "quickshell/lyra-capsule/bridge/lyra_capsule_bridge.py"
_spec = importlib.util.spec_from_file_location("lyra_capsule_bridge", _PATH)
bridge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bridge)


def _only(events):
    assert len(events) == 1
    return events[0]


def test_confirm_dangereux_devient_warn_avec_display():
    display = {"kind": "vms", "title": "Machines", "items": [{"id": "a", "label": "a"}], "pin": False}
    ev = _only(bridge.translate({"type": "ask", "kind": "confirm", "prompt": "Arreter a ?",
                                 "payload": {"danger": True, "display": display}}))
    assert ev["state"] == "warn" and ev["display"] == display
    assert ev["confirm"] == {"modify": True} and ev["askId"].startswith("ask-")


def test_confirm_simple_et_input():
    assert _only(bridge.translate({"type": "ask", "kind": "confirm", "prompt": "ok ?",
                                   "payload": {}}))["state"] == "confirm"
    assert _only(bridge.translate({"type": "ask", "kind": "input", "prompt": "nom ?",
                                   "payload": {}}))["state"] == "asking"


@pytest.mark.parametrize("message,state", [
    ({"type": "output", "kind": "lyra", "text": "salut"}, "speaking"),
    ({"type": "output", "kind": "tool_call", "tool": "vm_stop"}, "thinking"),
    ({"type": "output", "kind": "tool_result", "success": False, "text": "ko"}, "error"),
    ({"type": "result", "exit_code": 0, "executed": True}, "done"),
    ({"type": "result", "exit_code": 1, "executed": True}, "error"),
    ({"type": "error", "text": "boom"}, "error"),
])
def test_etats(message, state):
    assert _only(bridge.translate(message))["state"] == state


@pytest.mark.parametrize("message", [
    {"type": "pong"}, {"type": "ready", "status": "ok"}, {"type": "tasks", "active": []},
    {"type": "output", "kind": "info", "text": "x"},
])
def test_messages_ignores(message):
    assert bridge.translate(message) == []


@pytest.mark.parametrize("click,expected", [
    ({"type": "answer", "id": "confirm", "value": "o"}, {"type": "answer", "value": "o"}),
    ({"type": "answer", "id": "vm1", "value": "vm1"}, {"type": "answer", "value": "vm1"}),
    ({"type": "answer", "id": "volume", "value": 28},
     {"type": "answer", "value": "volume", "control": {"id": "volume", "value": 28}}),
    ({"type": "answer", "id": "x", "value": {"a": 1}}, None),
    ({"type": "answer", "id": "x"}, None),
    ({"type": "request", "value": "o"}, None),
])
def test_answer_message(click, expected):
    assert bridge.answer_message(click) == expected


def _st(state, **kw):
    return {"type": "state", "state": state, "session": "s", "ts": 1.0, **kw}


@pytest.mark.parametrize("message,state", [
    (_st("idle"), "idle"),
    (_st("thinking", label="vm_stop"), "thinking"),
    (_st("speaking"), "speaking"),
    (_st("ok"), "done"),
    (_st("error"), "error"),
    (_st("confirm", ask_id="a1", danger=False), "confirm"),
    (_st("confirm", ask_id="a1", danger=True), "warn"),
])
def test_etats_abonne(message, state):
    assert _only(bridge.translate_subscribed(message))["state"] == state


def test_confirm_abonne_porte_ask_id_display_et_label():
    display = {"kind": "slider", "id": "volume"}
    ev = _only(bridge.translate_subscribed(
        _st("confirm", ask_id="abc", danger=False, label="set_volume", display=display)))
    assert ev["askId"] == "abc" and ev["display"] == display
    assert "set_volume" in ev["title"] and ev["confirm"] == {"modify": False}


def test_thinking_sans_label_et_ack_et_inconnus():
    assert _only(bridge.translate_subscribed(_st("thinking")))["title"] == "Je réfléchis"
    ack = {"type": "answer_ack", "session": "s", "ask_id": "a", "value": "o", "source": "client"}
    assert bridge.translate_subscribed(ack) == [{"event": "voice_answer", "value": "o"}]
    assert bridge.translate_subscribed({"type": "subscribed", "max_subscribers": 8}) == []
    assert bridge.translate_subscribed(_st("bizarre")) == []


def test_answer_message_renvoie_ask_id():
    assert bridge.answer_message({"type": "answer", "id": "c", "value": "o"}, "a1") == \
        {"type": "answer", "value": "o", "ask_id": "a1"}
    ctl = bridge.answer_message({"type": "answer", "id": "volume", "value": 28}, "a1")
    assert ctl["ask_id"] == "a1" and ctl["control"] == {"id": "volume", "value": 28}


def _bridge_events(messages, mode="pending"):
    b = bridge.Bridge()
    b._mode = mode
    out = []
    for m in messages:
        out += b._dispatch(m)
    return b, out


def test_dispatch_subscribed_puis_state_retient_ask_id():
    b, out = _bridge_events([{"type": "subscribed", "max_subscribers": 8},
                             _st("confirm", ask_id="a9")])
    assert b._mode == "subscribed" and b._ask_id == "a9" and out[0]["askId"] == "a9"
    b._dispatch({"type": "answer_ack", "session": "s", "ask_id": "a9", "value": "o"})
    assert b._ask_id is None


def test_repli_ancien_demon_sur_erreur_sans_code():
    b, out = _bridge_events([{"type": "error", "text": "type inconnu: subscribe"},
                             {"type": "ask", "kind": "confirm", "prompt": "ok ?", "payload": {}}])
    assert b._mode == "legacy" and [e["state"] for e in out] == ["error", "confirm"]


def test_repli_sur_timeout_et_subscribed_tardif():
    b = bridge.Bridge()
    sentinel = object()
    b._mode, b._sock = "pending", sentinel
    b._on_subscribe_timeout(sentinel)
    assert b._mode == "legacy"
    b._dispatch({"type": "subscribed", "max_subscribers": 8})
    assert b._mode == "subscribed"


def test_erreurs_limit_stale_discretes(capsys):
    b, out = _bridge_events([{"type": "error", "code": "stale", "text": "x"}], "subscribed")
    assert out == [] and b._mode == "subscribed"
    b, out = _bridge_events([{"type": "error", "code": "limit", "text": "x"}], "pending")
    assert out == [] and b._retry_after == bridge.LIMIT_DELAY
    assert "stale" in capsys.readouterr().err


def test_reglage_mascotte_par_env(monkeypatch):
    monkeypatch.setenv("LYRA_CAPSULE_MASCOT", "ascii:owl")
    assert bridge.read_settings(None) == {"event": "settings", "mascot": "ascii:owl"}


def test_reglage_mascotte_depuis_yaml(monkeypatch, tmp_path):
    pytest.importorskip("yaml")
    monkeypatch.delenv("LYRA_CAPSULE_MASCOT", raising=False)
    cfg = tmp_path / "config.yaml"
    cfg.write_text("capsule:\n  mascot: cat\n", encoding="utf-8")
    assert bridge.read_settings(cfg)["mascot"] == "cat"
