"""
Lyra Daemon - Journal d'historique vocal (~/.lyra/history.jsonl).

Une ligne JSON par echange : horodatage, phrase telle que recue (transcription
pour un client vocal), canal, outil retenu, reussite. Aucun son, aucun argument
d'outil (ils peuvent porter des secrets) : seulement ce qu'il faut pour relire
« ce que j'ai dit, ce que Lyra a compris, et si ca a marche ».

Borne de taille : au-dela de MAX_BYTES le fichier devient history.jsonl.1
(un seul ancien exemplaire gardé, l'ancien .1 est ecrase). Ecriture en ajout,
jamais bloquante pour une requete : toute erreur est journalisee puis ignoree.

Ligne :
  {"ts": float, "session": str, "channel": "vocal|texte|api", "text": str,
   "tool": str, "understood": bool, "success": bool|None, "exit_code": int,
   "detail": str}
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("lyra.daemon.history")

HISTORY_PATH = Path.home() / ".lyra" / "history.jsonl"
MAX_BYTES = 2 * 1024 * 1024
MAX_TEXT = 500
MAX_DETAIL = 200
CHANNELS = {"vocal": "vocal", "repl": "texte", "oneshot": "texte", "api": "api"}

_LOCK = threading.Lock()


def channel_of(client: object) -> str:
    """Canal deduit du champ `client` du hello (inconnu -> « texte »)."""
    return CHANNELS.get(str(client or "").lower(), "texte")


def _clip(value: object, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def build_entry(*, session: str, channel: str, text: str, tool: str = "",
                success: Optional[bool] = None, exit_code: int = 0,
                detail: str = "", now: Optional[float] = None) -> dict:
    return {
        "ts": round(now if now is not None else time.time(), 3),
        "session": _clip(session, 60),
        "channel": channel if channel in ("vocal", "texte", "api") else "texte",
        "text": _clip(text, MAX_TEXT),
        "tool": _clip(tool, 80),
        "understood": bool(tool),
        "success": success,
        "exit_code": int(exit_code),
        "detail": _clip(detail, MAX_DETAIL),
    }


def _rotate_if_needed(path: Path, max_bytes: int) -> None:
    try:
        if path.stat().st_size < max_bytes:
            return
    except FileNotFoundError:
        return
    os.replace(path, path.with_name(path.name + ".1"))


def append(entry: dict, path: Path = HISTORY_PATH, max_bytes: int = MAX_BYTES) -> bool:
    """Ajoute une ligne. Ne leve jamais ; True si ecrite."""
    try:
        line = json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n"
        with _LOCK:
            path.parent.mkdir(parents=True, exist_ok=True)
            _rotate_if_needed(path, max_bytes)
            fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            try:
                os.write(fd, line.encode("utf-8"))
            finally:
                os.close(fd)
        return True
    except OSError as e:
        logger.warning("journal d'historique non ecrit : %s", e)
        return False


def read_recent(path: Path = HISTORY_PATH, limit: int = 200) -> list[dict]:
    """Dernieres lignes valides (la plus recente en dernier). Lignes illisibles ignorees."""
    out: list[dict] = []
    for p in (path.with_name(path.name + ".1"), path):
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for ln in lines:
            try:
                d = json.loads(ln)
            except ValueError:
                continue
            if isinstance(d, dict) and "ts" in d:
                out.append(d)
    return out[-limit:]


class Recorder:
    """Note, pendant une requete, l'outil retenu et son verdict (greffe sur RemoteUI)."""

    def __init__(self) -> None:
        self.tool = ""
        self.success: Optional[bool] = None
        self.detail = ""

    def tool_call(self, name: str) -> None:
        self.tool = name

    def tool_result(self, success: bool, raw_error: Optional[str]) -> None:
        self.success = bool(success)
        if not success and raw_error:
            self.detail = str(raw_error)

    def error(self, text: str) -> None:
        if not self.detail:
            self.detail = text
