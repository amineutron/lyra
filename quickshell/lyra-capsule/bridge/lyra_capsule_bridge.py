#!/usr/bin/env python3
"""Pont capsule Quickshell <-> demon Lyra.

Lance par shell.qml (Process, stdin/stdout en JSON-lines) :

    QML  -> pont  {"type": "answer", "id": str, "value": str|int}   clic dans la capsule
    pont -> QML   {"event": "state"|"display"|"voice_answer"|"settings"|"level"|"reset", ...}

Cote demon, le pont est un client du socket UNIX (lyra/daemon/protocol.py, JSON-lines) :
    pont -> demon {"type": "hello", "session": "capsule", "client": "capsule"}
                  {"type": "subscribe"}
                  {"type": "answer", "ask_id": str, "value": str}  (ou "control": {"id", "value"})
    demon -> pont subscribed / state / answer_ack / error{code}   (lyra/daemon/subscribe.py)

Mode abonne : le demon diffuse un `state` par changement d'etat (jamais le contenu des
reponses) ; la connexion est restreinte, le pont n'envoie rien d'autre que `answer`.
Repli : si `subscribed` n'arrive pas sous SUBSCRIBE_TIMEOUT (demon ancien), le pont reprend
l'ancien comportement (ask / output / progress, reponses sans ask_id) ; un `subscribed`
tardif rebascule en mode abonne.

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
RECONNECT_MAX = 30.0        # plafond du backoff exponentiel
LIMIT_DELAY = 30.0          # trop d'abonnes : on reessaie rarement
SUBSCRIBE_TIMEOUT = 1.5     # attente de `subscribed` avant le repli sur l'ancien protocole
STABLE_AFTER = 10.0         # une connexion plus longue remet le backoff a zero
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


def _label_suffix(label: str, prefix: str = " : ") -> str:
    return f"{prefix}{label}" if label else ""


def translate_subscribed(message: dict) -> list[dict]:
    """Un message du mode abonne (state / answer_ack / error) -> evenements capsule."""
    mtype = message.get("type")
    if mtype == "answer_ack":
        return [{"event": "voice_answer", "value": str(message.get("value", ""))}]
    if mtype != "state":
        return []   # subscribed, ready, pong, error : traites par le pont
    label = str(message.get("label") or "").strip()
    state = message.get("state")
    if state == "idle":
        return [_state("idle")]
    if state == "thinking":
        return [_state("thinking", title=f"J'exécute {label}" if label else "Je réfléchis")]
    if state == "speaking":
        return [_state("speaking", title="Voilà")]
    if state == "ok":
        return [_state("done", title="C'est fait")]
    if state == "error":
        return [_state("error", title="Ça n'a pas marché")]
    if state == "confirm":
        ask_id = message.get("ask_id")
        dangerous = bool(message.get("danger"))
        title = ("Action sensible" if dangerous else "Tu confirmes ?") + _label_suffix(label)
        event = _state("warn" if dangerous else "confirm", say=title, title=title,
                       confirm={"modify": False}, hints=["oui", "non"],
                       display=message.get("display"))
        if isinstance(ask_id, str) and ask_id:
            event["askId"] = ask_id
        return [event]
    return []


def answer_message(click: dict, ask_id: Optional[str] = None) -> Optional[dict]:
    """Clic QML -> message `answer` du demon (valeurs scalaires uniquement).

    `ask_id` : confirmation diffusee par le demon (mode abonne), renvoyee telle quelle.
    """
    value = click.get("value")
    if click.get("type") != "answer" or isinstance(value, (dict, list)) or value is None:
        return None
    if isinstance(click.get("id"), str) and isinstance(value, (int, float)) \
            and not isinstance(value, bool):
        # curseur : valeur numerique d'un controle ; extension additive du protocole
        reply = {"type": "answer", "value": click["id"],
                 "control": {"id": click["id"], "value": value}}
    else:
        reply = {"type": "answer", "value": str(value)}
    if ask_id:
        reply["ask_id"] = ask_id
    return reply


# ---------------------------------------------------------------------------
# E/S
# ---------------------------------------------------------------------------

class Bridge:
    def __init__(self) -> None:
        self._out_lock = threading.Lock()
        self._sock_lock = threading.Lock()
        self._sock: Optional[socket.socket] = None
        self._mode = "legacy"          # pending (attente de `subscribed`) | subscribed | legacy
        self._ask_id: Optional[str] = None   # confirmation diffusee en cours (mode abonne)
        self._retry_after = 0.0        # delai impose par le demon (limit)

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

    def _on_subscribe_timeout(self, sock: socket.socket) -> None:
        """Demon ancien : pas de `subscribed`, retour a l'ancien protocole."""
        with self._sock_lock:
            if self._sock is sock and self._mode == "pending":
                self._mode = "legacy"

    def _handle_error(self, message: dict) -> list[dict]:
        """Erreurs du mode abonne : discretes, jamais de boucle de reconnexion rapide."""
        code = message.get("code")
        if code == "limit":
            self._retry_after = LIMIT_DELAY
            print("capsule: trop d'abonnes au demon, nouvel essai plus tard", file=sys.stderr)
            with self._sock_lock:
                if self._sock is not None:   # le demon laisse la connexion ouverte : on la ferme
                    try:
                        self._sock.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
            return []
        if code in ("stale", "forbidden"):
            # reponse trop tardive (deja tranchee ailleurs, `answer_ack` verrouille la capsule)
            # ou refusee : message discret, pas de reconnexion
            print(f"capsule: reponse refusee par le demon ({code})", file=sys.stderr)
            return []
        if self._mode == "pending":      # demon ancien qui ne connait pas `subscribe`
            self._mode = "legacy"
        return translate(message) if self._mode == "legacy" else []

    def _dispatch(self, message: dict) -> list[dict]:
        mtype = message.get("type")
        if mtype == "subscribed":
            self._mode = "subscribed"
            return []
        if mtype == "error":
            return self._handle_error(message)
        if self._mode == "subscribed":
            events = translate_subscribed(message)
            if mtype == "state":
                ask_id = message.get("ask_id")
                self._ask_id = ask_id if message.get("state") == "confirm" \
                    and isinstance(ask_id, str) else None
            elif mtype == "answer_ack" and message.get("ask_id") == self._ask_id:
                self._ask_id = None
            return events
        return translate(message)

    def _serve(self, sock: socket.socket) -> None:
        with self._sock_lock:
            self._sock = sock
            self._mode = "pending"
            self._ask_id = None
        self._send_daemon({"type": "hello", "session": "capsule", "client": "capsule"})
        self._send_daemon({"type": "subscribe"})
        timer = threading.Timer(SUBSCRIBE_TIMEOUT, self._on_subscribe_timeout, args=(sock,))
        timer.daemon = True
        timer.start()
        try:
            with sock.makefile("r", encoding="utf-8", newline="\n") as stream:
                for line in stream:
                    try:
                        message = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(message, dict):
                        for event in self._dispatch(message):
                            self.emit(event)
        except OSError:
            pass
        finally:
            timer.cancel()
            with self._sock_lock:
                self._sock = None
            sock.close()

    def _daemon_loop(self) -> None:
        delay = RECONNECT_DELAY
        while True:
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.connect(str(socket_path()))
            except OSError:
                time.sleep(delay)
                delay = min(delay * 2, RECONNECT_MAX)
                continue
            started = time.monotonic()
            self._retry_after = 0.0
            self._serve(sock)
            delay = RECONNECT_DELAY if time.monotonic() - started >= STABLE_AFTER \
                else min(delay * 2, RECONNECT_MAX)
            self.emit({"event": "reset"})
            time.sleep(max(delay, self._retry_after))

    def run(self, lines: Iterable[str]) -> None:
        self.emit(read_settings(config_path()))
        threading.Thread(target=self._daemon_loop, daemon=True).start()
        for line in lines:
            try:
                click = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(click, dict):
                continue
            ask_id = self._ask_id if self._mode == "subscribed" else None
            if self._mode == "subscribed" and ask_id is None:
                continue   # rien a trancher : le demon repondrait `stale`
            reply = answer_message(click, ask_id)
            if reply is not None:
                self._send_daemon(reply)


if __name__ == "__main__":
    Bridge().run(sys.stdin)
