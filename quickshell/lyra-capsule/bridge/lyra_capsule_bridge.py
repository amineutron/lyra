#!/usr/bin/env python3
"""Pont capsule Quickshell <-> demon Lyra.

Lance par shell.qml (Process, stdin/stdout en JSON-lines) :

    QML  -> pont  {"type": "answer", "id": str, "value": str|int}   clic dans la capsule
    pont -> QML   {"event": "state"|"display"|"voice_answer"|"settings"|"level"|"reset", ...}

Cote demon, le pont est un client du socket UNIX (lyra/daemon/protocol.py, JSON-lines) :
    pont -> demon {"type": "hello", "session": "capsule", "client": "capsule"}
                  {"type": "answer", "value": str}   (confirmations : o / n / m ; choix : id propose)
    demon -> pont ask / output / progress / tool_result / result / error  (voir protocol.py)

Le pont ne decide rien : il traduit. Un clic renvoie toujours un id que le demon a lui-meme
propose (display.resolve_display_answer le revalide cote demon), jamais un texte libre.
Stdlib uniquement ; PyYAML est utilise s'il est installe, pour lire `capsule.mascot`.
"""
from __future__ import annotations

import itertools
import json
import os
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Any, Iterable, Optional

RECONNECT_DELAY = 2.0
_ASK_IDS = itertools.count(1)


def socket_path() -> Path:
    env = os.environ.get("LYRA_SOCKET")
    return Path(env) if env else Path.home() / ".lyra" / "lyra.sock"


def config_path() -> Optional[Path]:
    """config.yaml de Lyra : LYRA_CONFIG, puis XDG, puis ~/.lyra."""
    candidates = []
    if os.environ.get("LYRA_CONFIG"):
        candidates.append(Path(os.environ["LYRA_CONFIG"]))
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    candidates += [Path(xdg) / "lyra" / "config.yaml", Path.home() / ".lyra" / "config.yaml"]
    return next((p for p in candidates if p.is_file()), None)


def read_settings(path: Optional[Path]) -> dict:
    """Reglages de la capsule : `capsule.mascot` (random | ascii | ascii:<nom> | <nom>)."""
    settings: dict[str, Any] = {"event": "settings"}
    mascot = os.environ.get("LYRA_CAPSULE_MASCOT")
    if not mascot and path is not None:
        try:
            import yaml  # type: ignore
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            mascot = (data.get("capsule") or {}).get("mascot")
        except Exception:  # noqa: BLE001 - reglage optionnel : repli silencieux sur le defaut
            mascot = None
    if mascot:
        settings["mascot"] = str(mascot)
    return settings


# ---------------------------------------------------------------------------
# Traduction demon -> capsule (pure : testable sans socket)
# ---------------------------------------------------------------------------

def _state(state: str, **fields: Any) -> dict:
    return {"event": "state", "state": state, **fields}


def translate(message: dict) -> list[dict]:
    """Un message du demon -> 0..n evenements pour la capsule."""
    mtype = message.get("type")

    if mtype == "ask":
        payload = message.get("payload") or {}
        ask_id = f"ask-{next(_ASK_IDS)}"
        prompt = str(message.get("prompt") or "")
        display = payload.get("display") if isinstance(payload, dict) else None
        if message.get("kind") == "confirm":
            dangerous = bool(payload.get("danger")) if isinstance(payload, dict) else False
            return [_state("warn" if dangerous else "confirm", askId=ask_id, say=prompt,
                           title=prompt, confirm={"modify": True}, hints=["oui", "non"],
                           display=display)]
        return [_state("asking", askId=ask_id, say=prompt, title=prompt, display=display)]

    if mtype == "output":
        kind = message.get("kind")
        if kind in ("lyra", "lyra_tag"):
            return [_state("speaking", say=str(message.get("text") or ""), title="Voilà")]
        if kind == "tool_call":
            return [_state("thinking", title=f"J'exécute {message.get('tool', '')}".strip())]
        if kind == "tool_result" and message.get("success") is False:
            return [_state("error", title="Ça n'a pas marché",
                           say=str(message.get("text") or ""))]
        if kind == "error":
            return [_state("error", title="Ça n'a pas marché", say=str(message.get("text") or ""))]
        return []

    if mtype == "progress":
        return [_state("thinking", title=str(message.get("step") or "Je réfléchis"))]
    if mtype == "busy":
        return [_state("thinking", title=str(message.get("text") or "Je réfléchis"))]
    if mtype == "result":
        if message.get("exit_code", 0) == 0:
            return [_state("done", title="C'est fait")]
        return [_state("error", title="Ça n'a pas marché")]
    if mtype == "error":
        return [_state("error", title="Ça n'a pas marché", say=str(message.get("text") or ""))]
    if mtype == "answer_ack":   # propose : le demon signale qu'une reponse vocale a ete prise
        return [{"event": "voice_answer", "value": str(message.get("value", ""))}]
    return []   # ready, pong, tasks, health, analysis, memory_*


def answer_message(click: dict) -> Optional[dict]:
    """Clic QML -> message `answer` du demon (valeurs scalaires uniquement)."""
    value = click.get("value")
    if click.get("type") != "answer" or isinstance(value, (dict, list)) or value is None:
        return None
    if isinstance(click.get("id"), str) and isinstance(value, (int, float)) \
            and not isinstance(value, bool):
        # curseur : valeur numerique d'un controle ; extension additive du protocole
        return {"type": "answer", "value": click["id"],
                "control": {"id": click["id"], "value": value}}
    return {"type": "answer", "value": str(value)}


# ---------------------------------------------------------------------------
# E/S
# ---------------------------------------------------------------------------

class Bridge:
    def __init__(self) -> None:
        self._out_lock = threading.Lock()
        self._sock_lock = threading.Lock()
        self._sock: Optional[socket.socket] = None

    def emit(self, event: dict) -> None:
        line = json.dumps(event, ensure_ascii=False)
        with self._out_lock:
            sys.stdout.write(line + "\n")
            sys.stdout.flush()

    def _send_daemon(self, message: dict) -> None:
        data = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
        with self._sock_lock:
            if self._sock is None:
                print("capsule: demon injoignable, reponse perdue", file=sys.stderr)
                return
            try:
                self._sock.sendall(data)
            except OSError as exc:
                print(f"capsule: envoi au demon impossible: {exc}", file=sys.stderr)

    def _daemon_loop(self) -> None:
        while True:
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.connect(str(socket_path()))
            except OSError:
                time.sleep(RECONNECT_DELAY)
                continue
            with self._sock_lock:
                self._sock = sock
            self._send_daemon({"type": "hello", "session": "capsule", "client": "capsule"})
            try:
                with sock.makefile("r", encoding="utf-8", newline="\n") as stream:
                    for line in stream:
                        try:
                            message = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(message, dict):
                            for event in translate(message):
                                self.emit(event)
            except OSError:
                pass
            finally:
                with self._sock_lock:
                    self._sock = None
                sock.close()
            self.emit({"event": "reset"})
            time.sleep(RECONNECT_DELAY)

    def run(self, lines: Iterable[str]) -> None:
        self.emit(read_settings(config_path()))
        threading.Thread(target=self._daemon_loop, daemon=True).start()
        for line in lines:
            try:
                click = json.loads(line)
            except json.JSONDecodeError:
                continue
            reply = answer_message(click) if isinstance(click, dict) else None
            if reply is not None:
                self._send_daemon(reply)


if __name__ == "__main__":
    Bridge().run(sys.stdin)
