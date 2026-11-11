"""Sons de la capsule vocale : lecture non bloquante des 12 evenements.

SoundPlayer ne connait pas settings.py : il recoit une configuration simple
(SoundConfig ou dict avec les cles enabled / volume / pack / events, c'est-a-dire
ce que portent `capsule.sounds.*`). Les sons sont des WAV commites dans
lyra/client/assets/sounds/<pack>/<id>.wav (voir scripts/gen_sounds.py).

Securite : le chemin joue vient d'une table interne fermee (SOUND_IDS x PACKS),
jamais d'une entree externe ; la commande est une liste d'arguments (pas de shell).
Lecture par un lecteur systeme deja present (pw-play, paplay, aplay), sans
dependance Python supplementaire.
"""
from __future__ import annotations

import atexit
import logging
import math
import shutil
import subprocess
import sys
import tempfile
import threading
import wave
from array import array
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

SOUNDS_DIR = Path(__file__).resolve().parent / "assets" / "sounds"

# Table fermee des evenements : seuls ces ids peuvent etre joues.
SOUND_IDS: tuple[str, ...] = (
    "listen_start", "listen_end", "thinking", "speak_start", "ask", "confirm",
    "warn", "success", "error", "cancel", "choice", "pin",
)

# Jeux disponibles ("crystal" et "retro" viendront s'ajouter ici).
PACKS: tuple[str, ...] = ("soft",)
DEFAULT_PACK = "soft"

# Evenements qui coupent le son en cours au lieu de se superposer.
PRIORITY_EVENTS: frozenset[str] = frozenset({"warn", "error"})

# Lecteurs essayes dans l'ordre : (binaire, options avant le fichier).
PLAYERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("pw-play", ()),
    ("paplay", ()),
    ("aplay", ("-q",)),
)

DEFAULT_VOLUME = 0.35
MAX_VOLUME = 1.0           # jamais plus fort que la voix
SAFETY_TIMEOUT_S = 5.0     # un lecteur encore vivant apres ce delai est tue

_UNSET = object()


def clamp_volume(value: object, default: float = DEFAULT_VOLUME) -> float:
    """Ramene un volume quelconque dans [0, MAX_VOLUME] ; valeur invalide -> defaut."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return default
    try:
        volume = float(value)
    except ValueError:
        return default
    if math.isnan(volume):
        return default
    return max(0.0, min(MAX_VOLUME, volume))


@dataclass(frozen=True)
class SoundConfig:
    enabled: bool = True
    volume: float = DEFAULT_VOLUME
    pack: str = DEFAULT_PACK
    events: Mapping[str, bool] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, raw: Mapping | None) -> SoundConfig:
        """Construit une config depuis un dict (cles absentes = valeurs par defaut)."""
        raw = raw or {}
        events = raw.get("events") or {}
        return cls(
            enabled=bool(raw.get("enabled", True)),
            volume=clamp_volume(raw.get("volume", DEFAULT_VOLUME)),
            pack=str(raw.get("pack", DEFAULT_PACK)),
            events={str(k): bool(v) for k, v in events.items()}
            if isinstance(events, Mapping) else {},
        )


class SoundPlayer:
    """Joue les sons de la capsule sans jamais bloquer ni lever d'exception."""

    def __init__(self, config: SoundConfig | Mapping | None = None) -> None:
        self._config = (
            config if isinstance(config, SoundConfig) else SoundConfig.from_mapping(config)
        )
        self._player: object = _UNSET          # (chemin, options) | None, mis en cache
        self._procs: list[subprocess.Popen] = []
        self._lock = threading.Lock()
        self._scaled_dir: Path | None = None   # sons mis a l'echelle (volume < 1)

    @property
    def config(self) -> SoundConfig:
        return self._config

    def _pack(self) -> str:
        if self._config.pack in PACKS:
            return self._config.pack
        log.debug("jeu de sons inconnu %r, repli sur %s", self._config.pack, DEFAULT_PACK)
        return DEFAULT_PACK

    def _find_player(self) -> tuple[str, tuple[str, ...]] | None:
        if self._player is _UNSET:
            self._player = None
            for name, opts in PLAYERS:
                found = shutil.which(name)
                if found:
                    self._player = (found, opts)
                    break
            if self._player is None:
                log.debug("aucun lecteur audio (%s)", ", ".join(n for n, _ in PLAYERS))
        return self._player  # type: ignore[return-value]

    def _source_path(self, event_id: str) -> Path:
        return SOUNDS_DIR / self._pack() / f"{event_id}.wav"

    def _scaled_path(self, source: Path, volume: float) -> Path | None:
        """Copie du WAV avec les echantillons multiplies par `volume` (cache disque)."""
        if self._scaled_dir is None:
            self._scaled_dir = Path(tempfile.mkdtemp(prefix="lyra-sounds-"))
            atexit.register(shutil.rmtree, self._scaled_dir, ignore_errors=True)
        target = self._scaled_dir / f"{source.parent.name}-{source.stem}-{round(volume * 100)}.wav"
        if target.exists():
            return target
        try:
            with wave.open(str(source), "rb") as src:
                params = src.getparams()
                if params.sampwidth != 2:
                    return None
                pcm = array("h")
                pcm.frombytes(src.readframes(params.nframes))
            if sys.byteorder == "big":
                pcm.byteswap()
            scaled = array("h", (max(-32768, min(32767, round(s * volume))) for s in pcm))
            if sys.byteorder == "big":
                scaled.byteswap()
            with wave.open(str(target), "wb") as dst:
                dst.setparams(params)
                dst.writeframes(scaled.tobytes())
        except (OSError, wave.Error, EOFError) as exc:
            log.debug("mise a l'echelle impossible pour %s : %s", source.name, exc)
            return None
        return target

    def _stop_running(self) -> None:
        with self._lock:
            procs, self._procs = self._procs, []
        for proc in procs:
            _kill_if_running(proc)

    def _prune(self) -> None:
        with self._lock:
            self._procs = [p for p in self._procs if p.poll() is None]

    def play(self, event_id: str) -> bool:
        """Lance le son de `event_id` en arriere-plan. Renvoie True si un lecteur a demarre.

        Ignore sans exception : id inconnu, sons ou evenement desactive, fichier
        absent, aucun lecteur disponible, echec de lancement.
        """
        if event_id not in SOUND_IDS:
            log.debug("evenement sonore inconnu : %r", event_id)
            return False
        cfg = self._config
        if not cfg.enabled or not cfg.events.get(event_id, True):
            return False
        volume = clamp_volume(cfg.volume)
        if volume <= 0.0:
            return False
        source = self._source_path(event_id)
        if not source.is_file():
            log.debug("fichier son absent : %s", source)
            return False
        player = self._find_player()
        if player is None:
            return False
        path = source
        if volume < MAX_VOLUME:
            scaled = self._scaled_path(source, volume)
            if scaled is None:
                return False
            path = scaled

        if event_id in PRIORITY_EVENTS:
            self._stop_running()
        else:
            self._prune()
        binary, opts = player
        try:
            proc = subprocess.Popen(
                [binary, *opts, str(path)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except (OSError, ValueError) as exc:
            log.debug("lancement du lecteur impossible : %s", exc)
            return False
        with self._lock:
            self._procs.append(proc)
        timer = threading.Timer(SAFETY_TIMEOUT_S, _kill_if_running, args=(proc,))
        timer.daemon = True
        timer.start()
        return True

    def stop(self) -> None:
        """Coupe tous les sons en cours."""
        self._stop_running()


def _kill_if_running(proc: subprocess.Popen) -> None:
    """Tue le lecteur s'il tourne encore ; poll() recolte aussi les zombies."""
    try:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=1)
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.debug("arret du lecteur impossible : %s", exc)
