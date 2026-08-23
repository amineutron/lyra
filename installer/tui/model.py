"""Modele d'ecran alimente par les evenements du pipeline.

Le pipeline (thread worker) appelle handle_event() ; la boucle Live lit
snapshot() a chaque frame. Tout l'etat mutable vit ici, protege par un Lock.
Les Ask sont mis en file : la boucle UI les depile et repond via le broker.
"""
from __future__ import annotations

import queue
import threading
from collections import deque
from dataclasses import dataclass

from installer.core.events import (Ask, Event, Output, Progress, Result,
                                   StepChange)
from installer.core.pipeline import StepDef

LOG_MAX = 5


@dataclass(frozen=True)
class StepView:
    id: str
    label: str
    status: str = "wait"    # wait | run | ok | err | skip
    detail: str = ""
    elapsed: float = 0.0


@dataclass(frozen=True)
class Snapshot:
    steps: tuple[StepView, ...]
    logs: tuple[str, ...]
    nodes: tuple[str, ...]      # ids MCP connectes (graphe)
    done: bool
    ok: bool
    error: str


class UIModel:
    """Etat de l'ecran d'installation, thread-safe."""

    def __init__(self, pipeline: tuple[StepDef, ...]):
        self._lock = threading.Lock()
        self._steps: list[StepView] = [
            StepView(id=s.id, label=s.label) for s in pipeline
        ]
        self._logs: deque[str] = deque(maxlen=LOG_MAX)
        self._nodes: list[str] = []
        self._done = False
        self._ok = False
        self._error = ""
        self.asks: "queue.Queue[Ask]" = queue.Queue()

    # ── Reception des evenements (thread pipeline) ───────────────────

    def handle_event(self, event: Event) -> None:
        if isinstance(event, Output):
            self._on_output(event)
        elif isinstance(event, Progress):
            self._on_progress(event)
        elif isinstance(event, StepChange):
            self._on_step(event)
        elif isinstance(event, Ask):
            self.asks.put(event)
        elif isinstance(event, Result):
            with self._lock:
                self._done = True
                self._ok = event.ok
                self._error = event.error

    def _on_output(self, event: Output) -> None:
        line = event.line.strip()
        if not line:
            return
        with self._lock:
            self._logs.append(line)

    def _on_progress(self, event: Progress) -> None:
        with self._lock:
            self._replace_step(event.step_id, detail=event.detail)

    def _on_step(self, event: StepChange) -> None:
        with self._lock:
            kwargs: dict = {"status": event.status}
            if event.detail:
                kwargs["detail"] = event.detail
            if event.elapsed:
                kwargs["elapsed"] = event.elapsed
            self._replace_step(event.step_id, **kwargs)
            # Noeud MCP connecte des que son etape demarre
            if event.step_id.startswith("mcp_") and event.status == "run":
                node = event.step_id[4:]
                if node not in self._nodes:
                    self._nodes.append(node)

    def _replace_step(self, step_id: str, **kwargs) -> None:
        """Remplace la StepView visee par une copie modifiee (immutabilite)."""
        from dataclasses import replace
        for i, step in enumerate(self._steps):
            if step.id == step_id:
                self._steps[i] = replace(step, **kwargs)
                return

    # ── Lecture (boucle UI) ──────────────────────────────────────────

    def snapshot(self) -> Snapshot:
        with self._lock:
            return Snapshot(
                steps=tuple(self._steps),
                logs=tuple(self._logs),
                nodes=tuple(self._nodes),
                done=self._done,
                ok=self._ok,
                error=self._error,
            )
