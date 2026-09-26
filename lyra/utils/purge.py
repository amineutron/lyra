"""Purge des donnees gardees en clair (roadmap #54), logique pure et testee.

Trois magasins contiennent du texte venu de l'utilisateur (voir
docs/user/DATA_FLOWS.md) :

- ``data/session_history.db`` : requetes et reponses (SQLite) ;
- ``data/feedback.json`` : requetes notees et motifs appris du feedback ;
- ``~/.lyra/logs/errors/`` : arguments des outils MCP en echec.

La purge est une OPTION : rien n'est efface sans ``lyra --purge`` ou sans
``privacy.purge_on_stop: true``. Chaque purge se fait en trois temps : ``plan``
(ce qui serait efface, sans rien toucher), ``purge`` puis ``plan`` a nouveau,
qui doit tout donner a zero (verification).
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

SESSION_DB = Path("data") / "session_history.db"
FEEDBACK_JSON = Path("data") / "feedback.json"
ERROR_LOGS = Path(".lyra") / "logs" / "errors"
# champs du feedback qui portent du texte utilisateur ou des motifs tires de ce texte
_FEEDBACK_KEYS = ("interactions", "hits", "enrichments")


@dataclass(frozen=True)
class PurgeItem:
    """Un magasin et le nombre d'elements en clair qu'il contient."""

    label: str
    path: Path
    count: int
    unit: str


def _session_rows(db: Path) -> int:
    if not db.exists():
        return 0
    with sqlite3.connect(db) as conn:
        try:
            return conn.execute("SELECT COUNT(*) FROM session_history").fetchone()[0]
        except sqlite3.OperationalError:  # base vide, table jamais creee
            return 0


def _feedback_entries(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return 0
    if not isinstance(data, dict):
        return 0
    return sum(len(data.get(k) or ()) for k in _FEEDBACK_KEYS)


def _error_logs(folder: Path) -> list[Path]:
    return sorted(p for p in folder.glob("*.log") if p.is_file()) if folder.is_dir() else []


def plan(root: Path, home: Path) -> list[PurgeItem]:
    """Ce que contiennent les magasins, sans rien modifier."""
    errors = home / ERROR_LOGS
    return [
        PurgeItem("historique des echanges", root / SESSION_DB, _session_rows(root / SESSION_DB), "echanges"),
        PurgeItem("retours et motifs appris", root / FEEDBACK_JSON, _feedback_entries(root / FEEDBACK_JSON), "entrees"),
        PurgeItem("journaux d'erreurs MCP", errors, len(_error_logs(errors)), "fichiers"),
    ]


def _purge_session(db: Path) -> None:
    if not db.exists():
        return
    # DELETE plutot que supprimer le fichier : le demon garde une connexion ouverte
    # dessus, et ecrirait sinon dans un fichier supprime.
    with sqlite3.connect(db) as conn:
        try:
            conn.execute("DELETE FROM session_history")
        except sqlite3.OperationalError:
            return
    with sqlite3.connect(db) as conn:
        conn.execute("VACUUM")  # sinon les pages liberees gardent le texte


def _purge_feedback(path: Path) -> None:
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.update(interactions=[], hits={}, enrichments={})
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def purge(root: Path, home: Path) -> list[PurgeItem]:
    """Efface les trois magasins ; renvoie ce qu'ils contenaient avant."""
    before = plan(root, home)
    _purge_session(root / SESSION_DB)
    _purge_feedback(root / FEEDBACK_JSON)
    for log in _error_logs(home / ERROR_LOGS):
        log.unlink(missing_ok=True)
    return before


def is_clean(items: list[PurgeItem]) -> bool:
    return all(item.count == 0 for item in items)


def render(items: list[PurgeItem], title: str) -> str:
    lines = [title]
    lines += [f"  {item.label:<26} {item.count:>5} {item.unit:<9} {item.path}" for item in items]
    return "\n".join(lines)
