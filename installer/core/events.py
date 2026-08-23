"""Evenements du pipeline d'installation.

Vocabulaire aligne sur lyra/daemon/protocol.py : output / progress / ask /
result, plus 'step' pour l'avancement des etapes. Les deux frontaux (TUI et
app) consomment exactement ces evenements — aucune logique de rendu ici.
"""
from __future__ import annotations

import itertools
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass(frozen=True)
class Output:
    """Une ligne de sortie (log brut d'une commande)."""
    line: str


@dataclass(frozen=True)
class Progress:
    """Detail d'avancement d'une etape en cours (ex: paquet pip courant)."""
    step_id: str
    detail: str


@dataclass(frozen=True)
class StepChange:
    """Changement d'etat d'une etape : wait | run | ok | err | skip."""
    step_id: str
    status: str
    elapsed: float = 0.0
    detail: str = ""


@dataclass(frozen=True)
class Ask:
    """Question bloquante posee au frontal.

    kind : confirm | input | countdown (pairing Hue).
    """
    ask_id: str
    kind: str
    prompt: str
    default: Any = None
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Result:
    """Fin du pipeline."""
    ok: bool
    error: str = ""


Event = Output | Progress | StepChange | Ask | Result
Emit = Callable[[Event], None]


class AskBroker:
    """Pont bloquant question/reponse entre le pipeline et un frontal.

    Le pipeline appelle ask() (bloquant) ; le frontal recoit l'evenement
    Ask via emit puis appelle answer(ask_id, value) pour debloquer.
    """

    def __init__(self, emit: Emit, timeout: float = 600.0):
        self._emit = emit
        self._timeout = timeout
        self._counter = itertools.count(1)
        self._lock = threading.Lock()
        self._pending: dict[str, threading.Event] = {}
        self._answers: dict[str, Any] = {}

    def ask(self, kind: str, prompt: str, default: Any = None,
            extra: Optional[dict] = None) -> Any:
        ask_id = f"ask-{next(self._counter)}"
        done = threading.Event()
        with self._lock:
            self._pending[ask_id] = done
        self._emit(Ask(ask_id=ask_id, kind=kind, prompt=prompt,
                       default=default, extra=dict(extra or {})))
        if not done.wait(self._timeout):
            with self._lock:
                self._pending.pop(ask_id, None)
            raise TimeoutError(f"Aucune reponse au prompt '{prompt}'")
        with self._lock:
            return self._answers.pop(ask_id, default)

    def answer(self, ask_id: str, value: Any) -> bool:
        with self._lock:
            done = self._pending.pop(ask_id, None)
            if done is None:
                return False
            self._answers[ask_id] = value
        done.set()
        return True

    def confirm(self, prompt: str, default: bool = True) -> bool:
        return bool(self.ask("confirm", prompt, default))

    def input(self, prompt: str, default: str = "") -> str:
        return str(self.ask("input", prompt, default))
