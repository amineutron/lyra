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


def test_reglage_mascotte_par_env(monkeypatch):
    monkeypatch.setenv("LYRA_CAPSULE_MASCOT", "ascii:owl")
    assert bridge.read_settings(None) == {"event": "settings", "mascot": "ascii:owl"}


def test_reglage_mascotte_depuis_yaml(monkeypatch, tmp_path):
    pytest.importorskip("yaml")
    monkeypatch.delenv("LYRA_CAPSULE_MASCOT", raising=False)
    cfg = tmp_path / "config.yaml"
    cfg.write_text("capsule:\n  mascot: cat\n", encoding="utf-8")
    assert bridge.read_settings(cfg)["mascot"] == "cat"
