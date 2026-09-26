"""Purge verifiable des donnees en clair (roadmap #54), tout sur tmp_path."""
import json
import sqlite3
from pathlib import Path

import pytest

from lyra.client import purge_cmd
from lyra.utils import purge


def _seed(root: Path, home: Path) -> None:
    db = root / purge.SESSION_DB
    db.parent.mkdir(parents=True)
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE session_history (id INTEGER PRIMARY KEY, query TEXT, response TEXT)")
        conn.executemany("INSERT INTO session_history (query, response) VALUES (?, ?)",
                         [("allume la tele du client", "ok"), ("liste les vm", "3 vm")])
    (root / purge.FEEDBACK_JSON).write_text(json.dumps({
        "interactions": [{"query": "demarre la vm compta", "tool_name": "fedora.vm_start"}],
        "hits": {"allume": 3}, "enrichments": {"tele": {"type": "slang"}},
        "slang_dict_size": 12, "synonym_dict_size": 4,
    }), encoding="utf-8")
    errors = home / purge.ERROR_LOGS
    errors.mkdir(parents=True)
    (errors / "2026-09-27_vm_start.log").write_text("Arguments : {'vm': 'compta'}")
    (errors / "notes.txt").write_text("pas un journal d'erreur")


@pytest.fixture
def dirs(tmp_path):
    root, home = tmp_path / "lyra", tmp_path / "home"
    root.mkdir()
    home.mkdir()
    _seed(root, home)
    return root, home


def test_plan_compte_sans_rien_modifier(dirs):
    root, home = dirs
    items = purge.plan(root, home)
    assert [i.count for i in items] == [2, 3, 1]
    assert purge.plan(root, home) == items  # lecture seule


def test_purge_puis_verification_a_zero(dirs):
    root, home = dirs
    before = purge.purge(root, home)
    assert [i.count for i in before] == [2, 3, 1]
    assert purge.is_clean(purge.plan(root, home))


def test_purge_efface_le_texte_du_fichier_sqlite(dirs):
    root, home = dirs
    purge.purge(root, home)
    raw = (root / purge.SESSION_DB).read_bytes()
    assert b"client" not in raw  # VACUUM : pas de texte residuel dans les pages libres


def test_purge_garde_la_structure_et_les_autres_fichiers(dirs):
    root, home = dirs
    purge.purge(root, home)
    data = json.loads((root / purge.FEEDBACK_JSON).read_text(encoding="utf-8"))
    assert data["interactions"] == [] and data["hits"] == {} and data["enrichments"] == {}
    assert data["slang_dict_size"] == 12
    assert (home / purge.ERROR_LOGS / "notes.txt").exists()
    with sqlite3.connect(root / purge.SESSION_DB) as conn:  # table toujours la pour le demon
        assert conn.execute("SELECT COUNT(*) FROM session_history").fetchone()[0] == 0


def test_magasins_absents_ou_casses(tmp_path):
    root, home = tmp_path / "vide", tmp_path / "h"
    (root / "data").mkdir(parents=True)
    (root / purge.FEEDBACK_JSON).write_text("pas du json")
    assert purge.is_clean(purge.plan(root, home))
    purge.purge(root, home)  # ne leve pas


def test_commande_dry_run_ne_touche_a_rien(dirs, monkeypatch, capsys):
    root, home = dirs
    monkeypatch.setattr(purge_cmd, "_via_daemon", lambda dry_run: None)
    monkeypatch.setattr(Path, "home", lambda: home)
    assert purge_cmd.run(dry_run=True, assume_yes=False, root=root) == purge_cmd.EXIT_OK
    assert [i.count for i in purge.plan(root, home)] == [2, 3, 1]
    assert "Rien n'a ete efface" in capsys.readouterr().out


def test_commande_demande_confirmation(dirs, monkeypatch):
    root, home = dirs
    monkeypatch.setattr(purge_cmd, "_via_daemon", lambda dry_run: None)
    monkeypatch.setattr(Path, "home", lambda: home)
    code = purge_cmd.run(dry_run=False, assume_yes=False, root=root, confirm=lambda _q: "n")
    assert code == purge_cmd.EXIT_ABORTED
    assert not purge.is_clean(purge.plan(root, home))


def test_commande_purge_et_verifie(dirs, monkeypatch, capsys):
    root, home = dirs
    monkeypatch.setattr(purge_cmd, "_via_daemon", lambda dry_run: None)
    monkeypatch.setattr(Path, "home", lambda: home)
    assert purge_cmd.run(dry_run=False, assume_yes=True, root=root) == purge_cmd.EXIT_OK
    assert "Purge verifiee" in capsys.readouterr().out
    assert purge.is_clean(purge.plan(root, home))


def test_demon_oublie_le_feedback_en_memoire(monkeypatch):
    # sans ca, le demon reecrit l'ancien feedback sur disque apres la purge
    from lyra.daemon import server
    from lyra.rag_enhanced import feedback_loop

    class Loop:
        _save_timer = None
        _interactions = [{"query": "x"}]
        _hits = __import__("collections").Counter({"a": 1})
        _enrichments = {"a": {}}

    loop = Loop()
    monkeypatch.setattr(feedback_loop, "_instance", loop)
    server._forget_feedback_in_memory()
    assert loop._interactions == [] and not loop._hits and loop._enrichments == {}


def test_demon_purge_desactivee_par_defaut():
    from lyra.daemon.server import LyraDaemon
    assert LyraDaemon().purge_on_stop is False


def test_demon_trop_ancien_rien_n_est_efface(dirs, monkeypatch, capsys):
    root, home = dirs

    def old_daemon(dry_run):
        raise RuntimeError("type de message inconnu: purge")

    monkeypatch.setattr(purge_cmd, "_via_daemon", old_daemon)
    monkeypatch.setattr(Path, "home", lambda: home)
    assert purge_cmd.run(dry_run=False, assume_yes=True, root=root) == purge_cmd.EXIT_ERROR
    assert "restart lyra-daemon" in capsys.readouterr().out
    assert [i.count for i in purge.plan(root, home)] == [2, 3, 1]


@pytest.mark.parametrize("exc,absent", [
    (FileNotFoundError(), True), (ConnectionRefusedError(), True), (BlockingIOError(11, "saturé"), False),
])
def test_demon_absent_ou_injoignable(monkeypatch, exc, absent):
    # 2026-09-27 : demon vivant mais socket sature (BlockingIOError) -> ne pas purger dans son dos
    from lyra.daemon import protocol

    def boom(*_a, **_k):
        raise exc

    monkeypatch.setattr(protocol, "connect", boom)
    if absent:
        assert purge_cmd._via_daemon(dry_run=True) is None
    else:
        with pytest.raises(RuntimeError, match="injoignable"):
            purge_cmd._via_daemon(dry_run=True)
