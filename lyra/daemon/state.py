"""
Lyra Daemon - Etat persistant et diagnostic de crash.

Le demon ecrit ~/.lyra/daemon_state.json (pid, statut, heartbeat). Au
demarrage, le client compare cet etat a la realite (pid vivant ?) pour
determiner si le dernier arret etait propre ou un crash, et construit un
message d'accueil facon Lyra expliquant la raison (spec utilisateur).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

STATE_PATH = Path.home() / ".lyra" / "daemon_state.json"

# Statuts possibles du demon
STARTING = "starting"
READY = "ready"
STOPPED = "stopped"   # arret propre (SIGTERM/quit)


def write_state(status: str, reason: str = "", extra: Optional[dict] = None) -> None:
    """Ecrit l'etat du demon (atomique)."""
    data = {
        "pid": os.getpid(),
        "status": status,
        "reason": reason,
        "updated_at": time.time(),
    }
    if extra:
        data.update(extra)
    if STATE_PATH.exists():
        try:
            previous = json.loads(STATE_PATH.read_text())
            data.setdefault("started_at", previous.get("started_at"))
        except (json.JSONDecodeError, OSError):
            pass
    if status == STARTING:
        data["started_at"] = time.time()
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=STATE_PATH.parent, suffix=".tmp",
                                     delete=False, encoding="utf-8") as tmp:
        tmp.write(json.dumps(data, indent=2))
        tmp_path = Path(tmp.name)
    tmp_path.replace(STATE_PATH)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError, TypeError):
        return False


def read_crash_info() -> Optional[dict]:
    """Analyse l'etat laisse par le dernier demon.

    Returns:
        None si aucun demon n'a jamais tourne ou si l'arret etait propre.
        Sinon {"reason": str, "detail": str} decrivant le crash.
    """
    try:
        state = json.loads(STATE_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None

    status = state.get("status")
    pid = state.get("pid")

    if status == STOPPED:
        return None  # arret propre
    if pid and _pid_alive(pid):
        return None  # demon encore vivant (pas un crash)

    # Statut ready/starting mais process mort -> crash
    detail = _journal_hint()
    reason = "inconnue"
    if detail:
        lowered = detail.lower()
        if "oom" in lowered or "out of memory" in lowered or "memory" in lowered:
            reason = "memoire saturee"
        elif "killed" in lowered or "sigkill" in lowered:
            reason = "processus tue"
        elif "traceback" in lowered or "error" in lowered:
            reason = "erreur interne"
    if reason == "inconnue" and status == STARTING:
        reason = "echec au demarrage"
    return {"reason": reason, "detail": detail[:400]}


def _journal_hint() -> str:
    """Dernieres lignes du journal systemd du demon (vide si indisponible)."""
    try:
        result = subprocess.run(
            ["journalctl", "--user", "-u", "lyra-daemon", "-n", "20",
             "--no-pager", "-o", "cat"],
            capture_output=True, text=True, timeout=3,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


# ---------------------------------------------------------------------------
# Message d'accueil facon Lyra (immersion, spec utilisateur)
# ---------------------------------------------------------------------------

_GREETINGS = {
    "memoire saturee": (
        "Je reviens en ligne — j'ai manque de memoire pendant ton absence "
        "et j'ai du redemarrer. Tout est recharge, on reprend."
    ),
    "processus tue": (
        "Me revoila. Quelqu'un (ou quelque chose) m'a coupee net — "
        "probablement un kill. Je me suis rechargee, on continue."
    ),
    "erreur interne": (
        "Je reviens en ligne apres un plantage de mon cote. J'ai note "
        "l'erreur dans mes logs. Tout est operationnel a nouveau."
    ),
    "echec au demarrage": (
        "Mon dernier demarrage a echoue en cours de route. Cette fois "
        "c'est bon, je suis prete."
    ),
    "inconnue": (
        "Je reviens en ligne — je me suis arretee sans laisser de trace "
        "claire (coupure ou redemarrage machine ?). Tout est recharge."
    ),
}


def crash_greeting(crash: dict) -> str:
    """Message d'accueil template pour un crash donne (fallback sans LLM).

    Le client peut ensuite le faire reformuler par le modele LYRA quand le
    demon est pret, pour varier le ton.
    """
    return _GREETINGS.get(crash.get("reason", "inconnue"), _GREETINGS["inconnue"])
