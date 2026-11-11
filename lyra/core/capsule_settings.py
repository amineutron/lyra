"""
Lyra Core - Reglages de la capsule vocale (mascotte, sons).

Source unique des cles `capsule.*`, de leurs valeurs par defaut et de leur
validation. La capsule (Quickshell) lit ~/.lyra/settings.json ; cote Python
on expose :

    capsule_settings(settings) -> CapsuleSettings   (pure, tolerante)
    validate_capsule_value(key, value)              (stricte, pour set())

Aucune dependance vers settings.py (qui importe ce module).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

# Creatures du catalogue installer/assets/mascots.json (verifie par un test).
MASCOT_NAMES: tuple[str, ...] = (
    "bolt", "comet", "atom", "pinwheel", "radar", "drop", "pulse", "rocket",
    "firefly", "ball", "spark", "dart", "fan", "satellite", "dice",
    "owl", "cat", "turtle", "snail", "ghost", "robot", "golem", "lantern",
    "whale", "frog", "blob", "octopus", "moon", "bear", "wizard",
)
MASCOT_SPECIALS: tuple[str, ...] = ("random", "ascii")
MASCOT_CHOICES: tuple[str, ...] = MASCOT_SPECIALS + MASCOT_NAMES

SOUND_PACKS: tuple[str, ...] = ("soft", "crystal", "retro")
SOUND_EVENT_IDS: tuple[str, ...] = (
    "listen_start", "listen_end", "thinking", "speak_start", "ask", "confirm",
    "warn", "success", "error", "cancel", "choice", "pin",
)

# Valeurs par defaut (une seule definition)
DEFAULT_MASCOT = "random"
DEFAULT_SOUNDS_ENABLED = True
DEFAULT_SOUNDS_VOLUME = 0.35
DEFAULT_SOUNDS_PACK = "soft"
# `thinking` est coupe par defaut : trop bavard
DEFAULT_EVENT_ENABLED: Mapping[str, bool] = MappingProxyType(
    {event: event != "thinking" for event in SOUND_EVENT_IDS}
)
VOLUME_MIN, VOLUME_MAX = 0.0, 1.0

KEY_MASCOT = "capsule.mascot"
KEY_SOUNDS_ENABLED = "capsule.sounds.enabled"
KEY_SOUNDS_VOLUME = "capsule.sounds.volume"
KEY_SOUNDS_PACK = "capsule.sounds.pack"
KEY_EVENT_PREFIX = "capsule.sounds.events."

CAPSULE_KEYS: frozenset[str] = frozenset(
    {KEY_MASCOT, KEY_SOUNDS_ENABLED, KEY_SOUNDS_VOLUME, KEY_SOUNDS_PACK}
    | {KEY_EVENT_PREFIX + event for event in SOUND_EVENT_IDS}
)


def event_key(event_id: str) -> str:
    """Cle settings.json d'un evenement sonore."""
    return KEY_EVENT_PREFIX + event_id


# ---------------------------------------------------------------------------
# Validation unitaire (valeur -> valeur normalisee, ou None si invalide)
# ---------------------------------------------------------------------------

def _norm_mascot(value: Any) -> str | None:
    return value if isinstance(value, str) and value in MASCOT_CHOICES else None


def _norm_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _norm_volume(value: Any) -> float | None:
    # bool est un int en Python : on le refuse explicitement
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not math.isfinite(number) or not VOLUME_MIN <= number <= VOLUME_MAX:
        return None
    return number


def _norm_pack(value: Any) -> str | None:
    return value if isinstance(value, str) and value in SOUND_PACKS else None


def _normalizer_for(key: str):
    if key == KEY_MASCOT:
        return _norm_mascot
    if key == KEY_SOUNDS_VOLUME:
        return _norm_volume
    if key == KEY_SOUNDS_PACK:
        return _norm_pack
    if key == KEY_SOUNDS_ENABLED or key.startswith(KEY_EVENT_PREFIX):
        return _norm_bool
    return None


def validate_capsule_value(key: str, value: Any) -> Any:
    """Retourne la valeur normalisee d'une cle capsule.* ou leve ValueError.

    Les cles hors capsule.* sont renvoyees telles quelles (pas de contrainte).
    """
    if key not in CAPSULE_KEYS:
        return value
    normalized = _normalizer_for(key)(value)
    if normalized is None:
        raise ValueError(f"Valeur invalide pour {key}: {value!r}")
    return normalized


# ---------------------------------------------------------------------------
# Vue fusionnee
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CapsuleSettings:
    """Reglages capsule effectifs (defauts + valeurs utilisateur valides)."""

    mascot: str
    sounds_enabled: bool
    sounds_volume: float
    sounds_pack: str
    sounds_events: Mapping[str, bool]

    def event_enabled(self, event_id: str) -> bool:
        """Un evenement joue un son si les sons sont actifs ET l'evenement aussi."""
        return self.sounds_enabled and self.sounds_events.get(event_id, False)

    def to_dict(self) -> dict:
        """Structure JSON-serialisable (meme forme que settings.json)."""
        return {
            "mascot": self.mascot,
            "sounds": {
                "enabled": self.sounds_enabled,
                "volume": self.sounds_volume,
                "pack": self.sounds_pack,
                "events": dict(self.sounds_events),
            },
        }


def _lookup(settings: Any, key: str) -> Any:
    """Lit `key` (dot-notation) dans un UserSettings ou un dict imbrique."""
    if isinstance(settings, Mapping):
        node: Any = settings
        for part in key.split("."):
            if not isinstance(node, Mapping) or part not in node:
                return None
            node = node[part]
        return node
    getter = getattr(settings, "get", None)
    return getter(key) if callable(getter) else None


def capsule_settings(settings: Any = None) -> CapsuleSettings:
    """Fusionne les reglages capsule.* avec les defauts (fonction pure).

    `settings` : UserSettings, dict imbrique (contenu de settings.json) ou None.
    Une valeur absente ou invalide retombe sur le defaut, sans lever.
    """
    def pick(key: str, default: Any) -> Any:
        normalized = _normalizer_for(key)(_lookup(settings, key))
        return default if normalized is None else normalized

    events = {
        event: pick(event_key(event), DEFAULT_EVENT_ENABLED[event])
        for event in SOUND_EVENT_IDS
    }
    return CapsuleSettings(
        mascot=pick(KEY_MASCOT, DEFAULT_MASCOT),
        sounds_enabled=pick(KEY_SOUNDS_ENABLED, DEFAULT_SOUNDS_ENABLED),
        sounds_volume=pick(KEY_SOUNDS_VOLUME, DEFAULT_SOUNDS_VOLUME),
        sounds_pack=pick(KEY_SOUNDS_PACK, DEFAULT_SOUNDS_PACK),
        sounds_events=MappingProxyType(events),
    )
