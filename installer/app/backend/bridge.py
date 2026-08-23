"""Pont entre le pipeline d'installation (thread) et les clients SSE.

Le pipeline emet des dataclasses (installer.core.events) ; ce module les
serialise en dicts JSON-compatibles, les archive (un client SSE qui se
connecte apres le lancement recoit l'historique) et les diffuse a chaque
abonne via une queue dediee.
"""
from __future__ import annotations

import queue
import threading
from dataclasses import asdict
from typing import Any, Optional

from ...core.events import AskBroker, Ask, Event, Output, Progress, Result, StepChange
from ...core.pipeline import StepDef, build_pipeline, run_pipeline
from ...core.catalog import McpDef
from ...core.state import InstallState


def serialize_event(event: Event) -> dict[str, Any]:
    """Serialise un evenement du pipeline en dict JSON-compatible."""
    if isinstance(event, Output):
        return {"type": "output", "line": event.line}
    if isinstance(event, Progress):
        return {"type": "progress", "step_id": event.step_id, "detail": event.detail}
    if isinstance(event, StepChange):
        return {"type": "step", "step_id": event.step_id, "status": event.status,
                "elapsed": event.elapsed, "detail": event.detail}
    if isinstance(event, Ask):
        return {"type": "ask", "ask_id": event.ask_id, "kind": event.kind,
                "prompt": event.prompt, "default": event.default,
                "extra": dict(event.extra)}
    if isinstance(event, Result):
        return {"type": "result", "ok": event.ok, "error": event.error}
    return {"type": "unknown", "data": asdict(event)}  # pragma: no cover


class InstallBusyError(RuntimeError):
    """Une installation est deja en cours."""


class InstallManager:
    """Gere UNE installation a la fois + la diffusion des evenements."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running = False
        self._history: list[dict[str, Any]] = []
        self._subscribers: list[queue.Queue] = []
        self._broker: Optional[AskBroker] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    # ---- diffusion ------------------------------------------------------

    def _publish(self, payload: dict[str, Any]) -> None:
        with self._lock:
            self._history.append(payload)
            subscribers = list(self._subscribers)
        for q in subscribers:
            q.put(payload)

    def _emit(self, event: Event) -> None:
        self._publish(serialize_event(event))

    def subscribe(self) -> tuple[list[dict[str, Any]], "queue.Queue[dict[str, Any]]"]:
        """Retourne (historique, queue) ; la queue recoit les events futurs."""
        q: queue.Queue = queue.Queue()
        with self._lock:
            history = list(self._history)
            self._subscribers.append(q)
        return history, q

    def unsubscribe(self, q: "queue.Queue[dict[str, Any]]") -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    # ---- questions ------------------------------------------------------

    def answer(self, ask_id: str, value: Any) -> bool:
        broker = self._broker
        if broker is None:
            return False
        return broker.answer(ask_id, value)

    # ---- lancement ------------------------------------------------------

    def start(self, state: InstallState,
              selected: tuple[McpDef, ...]) -> tuple[StepDef, ...]:
        """Lance le pipeline en thread. Leve InstallBusyError si deja actif.

        Retourne la liste des etapes (pour la frise cote front) et publie
        aussi un evenement {type: steps} en tete de flux.
        """
        with self._lock:
            if self._running:
                raise InstallBusyError("une installation est deja en cours")
            self._running = True
            self._history = []

        steps = build_pipeline(state, selected)
        self._publish({
            "type": "steps",
            "steps": [{"id": s.id, "label": s.label} for s in steps],
        })
        self._broker = AskBroker(self._emit)

        def _run() -> None:
            try:
                run_pipeline(state, selected, self._emit, self._broker,
                             pipeline=steps)
            except Exception as exc:  # noqa: BLE001 — jamais de thread mort muet
                self._publish({"type": "result", "ok": False,
                               "error": f"erreur interne : {exc}"})
            finally:
                with self._lock:
                    self._running = False

        self._thread = threading.Thread(target=_run, name="install-pipeline",
                                        daemon=True)
        self._thread.start()
        return steps
