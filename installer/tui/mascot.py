"""Animation de la mascotte ASCII (frames de installer/assets/mascots.json).

Une entree mascotte = {n, c, ms, role, states: {idle|busy|work|ok|err|sleep:
[frames]}} ; une frame = liste de 5 chaines de 9 caracteres ASCII.
L'appelant cadence : chaque appel a next_frame() avance d'une frame.
"""
from __future__ import annotations

import os
import random
from typing import Any, Optional

_FALLBACK_FRAME = ["         "] * 5


class MascotAnimator:
    """Cycle les frames d'une mascotte, un etat a la fois."""

    def __init__(self, entry: dict[str, Any]):
        self._entry = dict(entry)
        self._states: dict[str, list[list[str]]] = dict(entry.get("states") or {})
        self._current_state = "idle"
        self._index = 0

    @property
    def name(self) -> str:
        return str(self._entry.get("n", "?"))

    @property
    def color_code(self) -> str:
        return str(self._entry.get("c", ""))

    @property
    def interval_ms(self) -> int:
        return int(self._entry.get("ms", 100))

    def next_frame(self, state_name: str) -> str:
        """Texte 5 lignes de la frame courante, puis avance d'une frame.

        Un changement d'etat repart a la premiere frame de cet etat.
        Etat inconnu -> fallback sur idle, puis frame vide.
        """
        frames = self._states.get(state_name) or self._states.get("idle") or []
        if state_name != self._current_state:
            self._current_state = state_name
            self._index = 0
        if not frames:
            return "\n".join(_FALLBACK_FRAME)
        frame = frames[self._index % len(frames)]
        self._index = (self._index + 1) % len(frames)
        return "\n".join(frame)


def pick_mascot(mascots: dict[str, list[dict[str, Any]]],
                seed: Optional[int] = None) -> Optional[MascotAnimator]:
    """Choisit une mascotte stable dans la famille 'fast' (seed = PID).

    Retourne None si le catalogue de mascottes est vide.
    """
    pool = mascots.get("fast") or mascots.get("slow") or []
    if not pool:
        return None
    rng = random.Random(seed if seed is not None else os.getpid())
    return MascotAnimator(rng.choice(pool))
