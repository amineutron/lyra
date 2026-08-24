"""
Lyra Client - Cycle de vie du demon cote client.

Spec utilisateur : si le demon est mort, le client previent (notification +
message d'accueil facon Lyra expliquant la raison du crash), le relance
(systemd d'abord, spawn direct sinon), et bascule en standalone si le demon
refuse de demarrer.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from lyra.daemon import state as daemon_state
from lyra.daemon.protocol import SOCKET_PATH, LineChannel, connect

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DAEMON_LOG = Path.home() / ".lyra" / "logs" / "daemon.log"
START_TIMEOUT = 240.0  # init complete (modeles + ChromaDB) ~15-25s, marge large


def try_connect() -> Optional[LineChannel]:
    try:
        return connect(SOCKET_PATH)
    except OSError:
        return None


def _systemd_unit_exists() -> bool:
    try:
        result = subprocess.run(
            ["systemctl", "--user", "cat", "lyra-daemon.service"],
            capture_output=True, timeout=3,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _notify_crash(reason: str) -> None:
    """Notification desktop best-effort (spec: prevenir en cas de crash)."""
    try:
        subprocess.run(
            ["notify-send", "-a", "Lyra", "Lyra a redemarre",
             f"Raison du dernier arret : {reason}"],
            capture_output=True, timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def start_daemon() -> bool:
    """Demarre le demon (systemd si l'unit existe, sinon spawn detache)."""
    if _systemd_unit_exists():
        try:
            result = subprocess.run(
                ["systemctl", "--user", "start", "lyra-daemon.service"],
                capture_output=True, timeout=10,
            )
            if result.returncode == 0:
                return True
        except (OSError, subprocess.TimeoutExpired):
            pass
        # systemd a echoue -> tenter le spawn direct quand meme

    DAEMON_LOG.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(DAEMON_LOG, "a") as log:
            subprocess.Popen(
                [sys.executable, "-m", "lyra.daemon"],
                cwd=REPO_ROOT,
                stdout=log,
                stderr=log,
                start_new_session=True,  # survit a la fin du client
            )
        return True
    except OSError:
        return False


def wait_for_daemon(timeout: float = START_TIMEOUT,
                    on_wait=None) -> Optional[LineChannel]:
    """Attend que le socket accepte les connexions."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        channel = try_connect()
        if channel is not None:
            return channel
        if on_wait:
            on_wait()
        time.sleep(0.5)
    return None


def ensure_daemon(on_wait=None) -> tuple[Optional[LineChannel], Optional[str]]:
    """Connexion au demon, en le (re)lancant si besoin.

    Returns:
        (channel, greeting) — greeting est le message d'accueil facon Lyra a
        afficher si le demon avait crashe (None sinon). channel est None si le
        demon n'a pas pu demarrer (le client doit basculer en standalone).
    """
    channel = try_connect()
    if channel is not None:
        return channel, None

    crash = daemon_state.read_crash_info()
    greeting = None
    if crash is not None:
        greeting = daemon_state.crash_greeting(crash)
        _notify_crash(crash.get("reason", "inconnue"))

    if not start_daemon():
        return None, greeting

    channel = wait_for_daemon(on_wait=on_wait)
    return channel, greeting
