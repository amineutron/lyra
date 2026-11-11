"""
Lyra Daemon - Protocole client/serveur.

JSON-lines sur socket UNIX (~/.lyra/lyra.sock). Chaque ligne = un message.

Client -> demon :
  {"type": "hello",  "session": str, "client": "oneshot|repl|vocal"}
  {"type": "request", "text": str, "options": {"mode","yes","verbose","interactive"}}
  {"type": "answer",  "value": str}          # reponse a un "ask"
  {"type": "tool",    "name": str, "arguments": dict,
                      "options": {"confirmed": bool, "unattended": bool}}
                                             # execution directe d'un outil MCP, sans
                                             # modele (neutroncore, roadmap #73) ;
                                             # un outil dangereux non confirme -> "ask" ;
                                             # unattended (automatisations) : seuls les
                                             # outils de PERFORMANCE_TOOLS, jamais de "ask"
  {"type": "analyze", "text": str}           # que ferait Lyra de cette phrase ? Regles
                                             # seules, sans execution ni effet de bord
  {"type": "memory_list",   "store"?: "conversations|feedback|vocabulary", "limit"?: int}
  {"type": "memory_update", "id": str, "text": str, "store"?: str}
  {"type": "memory_delete", "id": str, "store"?: str}
  {"type": "memory_add",    "word": str, "means": [str], "store"?: "vocabulary"}
                                             # memoire editable (lyra/daemon/memory.py) :
                                             # ids stricts, ecriture atomique, sans modele
  {"type": "tasks_poll"}
  {"type": "health"}
  {"type": "ping"}

Demon -> client :
  {"type": "ready",   "status": str, "uptime": float}
  {"type": "output",  "kind": "info|success|warning|error|lyra|lyra_tag",
                      "text": str}
  {"type": "output",  "kind": "tool_call", "tool": str, "arguments": dict,
                      "vm_state": dict|None}
  {"type": "output",  "kind": "tool_result", "text": str, "success": bool,
                      "raw_error": str|None}
  {"type": "progress", "step": str, "data": dict}
  {"type": "ask",     "kind": "confirm|input", "prompt": str, "payload": dict}
                      # confirm : payload = {"tool", "arguments", "danger"} et, si
                      # l'outil s'y prete, "display" (champ additif, ignore par les
                      # clients existants) : description declarative pour la capsule
                      #   {"kind": "tv|vms|lights|choices|sessions", "title": str,
                      #    "items": [{"id": str, "label": str, "value"?: scalaire,
                      #               "state"?: str, "selected"?: bool}],
                      #    "controls"?: [{"type": "slider", "id": str, "min": int,
                      #                   "max": int, "value": int}],
                      #    "pin": false}
                      # (lyra/daemon/display.py). Tout est du TEXTE d'affichage. Un
                      # clic revient par le message "answer" existant ; sa valeur doit
                      # etre validee par display.resolve_display_answer() contre les
                      # items[].id proposes, jamais executee ni interpretee telle quelle.
  {"type": "result",  "exit_code": int, "executed": bool}
  {"type": "analysis", "found": bool, "tool": str, "arguments": dict,
                       "missing_args": list, "confidence": float, "source": "rule",
                       "dangerous": bool, "destructive": bool, "performance": bool,
                       "compound": bool,   # plusieurs actions dans la phrase : une seule retenue
                       "warnings": list}
  {"type": "memory_items", "items": list}
  {"type": "memory_done",  "op": "update|delete|add", "id": str, "store": str,
                           "restart_needed": bool}   # vocabulaire : lu au demarrage
  {"type": "error", "text": str, "code"?: "invalid|not_found|internal"}  # memory_* seulement
  {"type": "tasks",   "active": list, "errors": list, "notifications": list}
  {"type": "health",  "data": dict}
  {"type": "pong"}
  {"type": "busy",    "text": str}
  {"type": "error",   "text": str}
"""

from __future__ import annotations

import json
import socket
import threading
from pathlib import Path
from typing import Optional

SOCKET_PATH = Path.home() / ".lyra" / "lyra.sock"

# Timeout d'attente d'une reponse client a un "ask" (confirmations)
ASK_TIMEOUT = 120.0


class ChannelClosed(Exception):
    """La connexion a ete fermee par l'autre extremite."""


class LineChannel:
    """Canal JSON-lines bidirectionnel au-dessus d'un socket connecte."""

    def __init__(self, sock: socket.socket):
        self._sock = sock
        self._rfile = sock.makefile("r", encoding="utf-8", newline="\n")
        self._wlock = threading.Lock()

    def send(self, message: dict) -> None:
        data = (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")
        with self._wlock:
            try:
                self._sock.sendall(data)
            except (BrokenPipeError, OSError) as e:
                raise ChannelClosed(str(e)) from e

    def recv(self, timeout: Optional[float] = None) -> dict:
        """Lit un message. Leve ChannelClosed sur EOF, TimeoutError sur timeout."""
        self._sock.settimeout(timeout)
        try:
            line = self._rfile.readline()
        except socket.timeout as e:
            raise TimeoutError("pas de message recu dans le delai") from e
        except OSError as e:
            raise ChannelClosed(str(e)) from e
        if not line:
            raise ChannelClosed("EOF")
        try:
            message = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"message illisible: {line[:120]!r}") from e
        if not isinstance(message, dict) or "type" not in message:
            raise ValueError(f"message sans type: {line[:120]!r}")
        return message

    def close(self) -> None:
        try:
            self._rfile.close()
        except OSError:
            pass
        try:
            self._sock.close()
        except OSError:
            pass


def connect(socket_path: Path = SOCKET_PATH, timeout: float = 3.0) -> LineChannel:
    """Ouvre une connexion client vers le demon. Leve OSError si indisponible."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect(str(socket_path))
    return LineChannel(sock)
