#!/usr/bin/env python3
"""Synthetise les sons de la capsule vocale de Lyra (WAV 16 bits mono 44100 Hz).

Usage :
    python3 scripts/gen_sounds.py                    # regenere le jeu "soft" dans le depot
    python3 scripts/gen_sounds.py --out /tmp/sons    # ailleurs

Aucune dependance : modules standard `wave`, `math` et `array`. Le calcul est
deterministe (memes octets a chaque run, sur toute plateforme IEEE 754) : un test
regenere les fichiers et les compare a ceux qui sont commites.

Synthese : notes MIDI (hz = 440 * 2^((m-69)/12)), onde sinus, attaque 20 ms,
decroissance exponentielle, filtre passe-bas une pole a 2400 Hz, pic normalise a
-6 dBFS, fondu de sortie final de 10 ms.

Structure ouverte : PACKS associe un nom de jeu a sa table d'evenements. Les jeux
"crystal" et "retro" viendront s'y ajouter sans toucher au reste.
"""
from __future__ import annotations

import argparse
import math
import sys
import wave
from array import array
from pathlib import Path

SAMPLE_RATE = 44100
ATTACK_S = 0.020
RELEASE_TAIL_S = 0.020      # la note sonne un peu au-dela de sa duree nominale
FADE_OUT_S = 0.010          # fondu final de chaque note et du fichier (anti-clic)
LOWPASS_HZ = 2400.0
PEAK_DBFS = -6.0
DECAY_TIME_CONSTANTS = 3.0  # a la fin de la note, l'enveloppe vaut e^-3 (5 %)
DEFAULT_PACK = "soft"
DEFAULT_OUT_ROOT = Path(__file__).resolve().parent.parent / "lyra" / "client" / "assets" / "sounds"

# (midi, debut en s, duree en s)
Note = tuple[int, float, float]

SOFT_EVENTS: dict[str, list[Note]] = {
    "listen_start": [(76, 0.0, 0.14), (81, 0.12, 0.22)],
    "listen_end": [(81, 0.0, 0.12), (76, 0.11, 0.2)],
    "thinking": [(64, 0.0, 0.18), (64, 0.28, 0.18), (67, 0.56, 0.3)],
    "speak_start": [(72, 0.0, 0.2)],
    "ask": [(79, 0.0, 0.14), (84, 0.14, 0.3)],
    "confirm": [(72, 0.0, 0.12), (76, 0.14, 0.12), (79, 0.28, 0.28)],
    "warn": [(62, 0.0, 0.18), (58, 0.2, 0.18), (62, 0.42, 0.18), (58, 0.62, 0.3)],
    "success": [(72, 0.0, 0.12), (76, 0.1, 0.12), (79, 0.2, 0.12), (84, 0.3, 0.4)],
    "error": [(63, 0.0, 0.18), (57, 0.16, 0.4)],
    "cancel": [(79, 0.0, 0.1), (72, 0.09, 0.2)],
    "choice": [(93, 0.0, 0.06)],
    "pin": [(88, 0.0, 0.05), (93, 0.09, 0.07)],
}

PACKS: dict[str, dict[str, list[Note]]] = {
    "soft": SOFT_EVENTS,
}


def midi_to_hz(midi: int) -> float:
    return 440.0 * 2.0 ** ((midi - 69) / 12.0)


def _note_samples(midi: int, duration: float) -> list[float]:
    """Une note : sinus x enveloppe (attaque lineaire, decroissance exponentielle)."""
    hz = midi_to_hz(midi)
    total = int(round((duration + RELEASE_TAIL_S) * SAMPLE_RATE))
    attack = max(1, int(round(ATTACK_S * SAMPLE_RATE)))
    fade = max(1, int(round(FADE_OUT_S * SAMPLE_RATE)))
    tau = duration / DECAY_TIME_CONSTANTS
    out = []
    for i in range(total):
        t = i / SAMPLE_RATE
        env = math.exp(-t / tau)
        if i < attack:
            env *= i / attack
        remaining = total - 1 - i
        if remaining < fade:
            env *= remaining / fade
        out.append(math.sin(2.0 * math.pi * hz * t) * env)
    return out


def _lowpass(samples: list[float], cutoff_hz: float = LOWPASS_HZ) -> list[float]:
    """Filtre passe-bas une pole : y += a * (x - y)."""
    alpha = 1.0 - math.exp(-2.0 * math.pi * cutoff_hz / SAMPLE_RATE)
    y = 0.0
    out = []
    for x in samples:
        y += alpha * (x - y)
        out.append(y)
    return out


def render_samples(notes: list[Note]) -> list[float]:
    """Melange les notes, filtre, normalise a PEAK_DBFS et applique le fondu final."""
    end = max(start + dur + RELEASE_TAIL_S for _, start, dur in notes)
    mix = [0.0] * int(round(end * SAMPLE_RATE))
    for midi, start, dur in notes:
        offset = int(round(start * SAMPLE_RATE))
        for i, v in enumerate(_note_samples(midi, dur)):
            if offset + i < len(mix):
                mix[offset + i] += v
    mix = _lowpass(mix)
    peak = max(abs(v) for v in mix) or 1.0
    scale = (10.0 ** (PEAK_DBFS / 20.0)) / peak
    mix = [v * scale for v in mix]
    fade = min(len(mix), max(1, int(round(FADE_OUT_S * SAMPLE_RATE))))
    for k in range(fade):
        mix[len(mix) - 1 - k] *= k / fade
    return mix


def to_pcm16(samples: list[float]) -> bytes:
    """Float [-1, 1] -> PCM 16 bits little-endian."""
    pcm = array("h", (max(-32768, min(32767, round(v * 32767))) for v in samples))
    if sys.byteorder == "big":
        pcm.byteswap()
    return pcm.tobytes()


def write_wav(path: Path, notes: list[Note]) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(to_pcm16(render_samples(notes)))


def generate_pack(pack: str, out_dir: Path) -> list[Path]:
    """Ecrit <out_dir>/<id>.wav pour chaque evenement du jeu ; renvoie les chemins."""
    if pack not in PACKS:
        raise ValueError(f"jeu inconnu : {pack!r} (disponibles : {', '.join(sorted(PACKS))})")
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for event_id, notes in PACKS[pack].items():
        path = out_dir / f"{event_id}.wav"
        write_wav(path, notes)
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pack", default=DEFAULT_PACK, choices=sorted(PACKS))
    parser.add_argument("--out", type=Path, default=None,
                        help="repertoire racine de sortie (defaut : lyra/client/assets/sounds)")
    args = parser.parse_args(argv)
    root = args.out if args.out is not None else DEFAULT_OUT_ROOT
    for path in generate_pack(args.pack, root / args.pack):
        print(f"{path} ({path.stat().st_size} octets)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
