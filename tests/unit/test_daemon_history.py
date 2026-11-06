"""Journal d'historique vocal (~/.lyra/history.jsonl) : format, bornes, rotation, branchement du demon."""
from __future__ import annotations

import json
import os
import stat
from types import SimpleNamespace as N

import pytest

from lyra.daemon import history
from lyra.daemon import server as srv
from lyra.daemon.remote_ui import RemoteUI


def test_canaux():
    assert history.channel_of("vocal") == "vocal"
    assert history.channel_of("repl") == "texte" and history.channel_of("oneshot") == "texte"
    assert history.channel_of("api") == "api" and history.channel_of(None) == "texte"
    assert history.channel_of("inconnu") == "texte"


def test_entree_bornee_et_nettoyee():
    e = history.build_entry(session="s", channel="vocal", text="  allume\n la   tele " + "x" * 900,
                            tool="tv.power_on", success=True, detail="d" * 900, now=12.34567)
    assert e["ts"] == 12.346 and e["understood"] is True and e["success"] is True
    assert len(e["text"]) <= history.MAX_TEXT and "\n" not in e["text"] and e["text"].startswith("allume la tele")
    assert len(e["detail"]) <= history.MAX_DETAIL
    assert history.build_entry(session="s", channel="?", text="x")["channel"] == "texte"
    assert history.build_entry(session="s", channel="vocal", text="x")["understood"] is False


def test_ajout_une_ligne_par_echange_droits_0600(tmp_path):
    p = tmp_path / "sous" / "history.jsonl"
    for i in range(3):
        assert history.append(history.build_entry(session="s", channel="texte", text=f"phrase {i}"), p)
    lignes = p.read_text(encoding="utf-8").splitlines()
    assert [json.loads(x)["text"] for x in lignes] == ["phrase 0", "phrase 1", "phrase 2"]
    assert stat.S_IMODE(os.stat(p).st_mode) == 0o600


def test_rotation_un_seul_ancien_fichier(tmp_path):
    p = tmp_path / "history.jsonl"
    e = history.build_entry(session="s", channel="texte", text="x" * 100)
    for _ in range(40):
        history.append(e, p, max_bytes=1000)
    assert p.stat().st_size < 1000 + 400
    assert (tmp_path / "history.jsonl.1").is_file() and not (tmp_path / "history.jsonl.2").exists()
    assert len(history.read_recent(p, 1000)) <= 40


def test_ecriture_impossible_ne_leve_pas(tmp_path):
    bloc = tmp_path / "fichier"
    bloc.write_text("x")
    assert history.append({"ts": 1}, bloc / "history.jsonl") is False     # le « dossier » est un fichier


def test_lecture_ignore_les_lignes_illisibles(tmp_path):
    p = tmp_path / "history.jsonl"
    p.write_text('{"ts": 1, "text": "a"}\nnot json\n[1]\n{"ts": 2, "text": "b"}\n', encoding="utf-8")
    assert [d["text"] for d in history.read_recent(p)] == ["a", "b"]
    assert history.read_recent(tmp_path / "absent.jsonl") == []


def test_recorder_via_remote_ui():
    envoyes = []
    canal = N(send=lambda m: envoyes.append(m))
    rec = history.Recorder()
    ui = RemoteUI(canal, rec)
    ui.note_tool("tv.power_on")
    ui.tool_result("boom", success=False, raw_error="TV injoignable")
    ui.error("zut")
    assert (rec.tool, rec.success, rec.detail) == ("tv.power_on", False, "TV injoignable")
    assert envoyes == [{"type": "output", "kind": "tool_result", "text": "boom", "success": False,
                        "raw_error": "TV injoignable"}, {"type": "output", "kind": "error", "text": "zut"}]


def test_remote_ui_sans_recorder_inchange():
    envoyes = []
    ui = RemoteUI(N(send=lambda m: envoyes.append(m)))
    ui.note_tool("x")
    ui.tool_call("x", {})
    ui.tool_result("ok")
    assert [m["kind"] for m in envoyes] == ["tool_call", "tool_result"]


@pytest.mark.parametrize("tool,success,code,attendu_succes,attendu_detail", [
    ("tv.power_on", True, 0, True, ""),
    ("fedora.vm_stop", False, 1, False, "refuse"),
    ("fedora.vm_start", None, 0, True, ""),       # tache de fond lancee : pas de verdict immediat
    ("", None, 0, None, ""),                      # rien compris / question de culture
    ("fedora.vm_stop", None, 2, None, "annule"),  # l'utilisateur a dit non
])
def test_journal_du_demon(tmp_path, monkeypatch, tool, success, code, attendu_succes, attendu_detail):
    p = tmp_path / "history.jsonl"
    monkeypatch.setattr(history, "HISTORY_PATH", p)
    rec = history.Recorder()
    rec.tool, rec.success = tool, success
    rec.detail = "refuse" if attendu_detail == "refuse" else ""
    srv.LyraDaemon._journal_request({"type": "request", "text": "bonjour"}, "sess", "vocal", rec, code)
    (e,) = history.read_recent(p)
    assert e["text"] == "bonjour" and e["channel"] == "vocal" and e["session"] == "sess"
    assert e["tool"] == tool and e["success"] is attendu_succes and e["exit_code"] == code
    assert e["detail"] == attendu_detail and e["understood"] is bool(tool)


def test_journal_du_demon_ne_leve_jamais(monkeypatch):
    monkeypatch.setattr(history, "append", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    srv.LyraDaemon._journal_request({"text": "a"}, "s", None, history.Recorder(), 0)
