"""
Metriques de la scene Iron Man
==============================

Enregistre les timings de chaque etape (phases + sous-etapes) pour les
5 derniers lancements, afin de suivre les regressions de latence et de
comprendre les problemes.

Fichier: ~/.lyra/ironman_metrics.json

Structure d'un run:
    {
        "timestamp": "2026-07-22T19:30:00",
        "run_type": "full" | "sub-scene",
        "selection": [0, 1, 2, 3, 4, 5],
        "success": true,
        "total_s": 33.2,
        "time_to_first_effect_s": 0.4,
        "steps": {
            "phase0": {"duration_s": 0.5, "success": true},
            "phase1": {"duration_s": 3.0, "success": true,
                        "lights_latency_ms": 169, ...},
            ...
        },
        "markers": {"first_visible_effect": 0.42, "music_started": 5.1}
    }
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

METRICS_FILE = Path.home() / ".lyra" / "ironman_metrics.json"
MAX_RUNS = 5

# Cles des resultats de phase conservees dans les metriques
_STEP_EXTRA_KEYS = (
    "latency_ms", "lights_off", "tv_off", "tv_action", "ambilight_off",
    "pc_screens_off", "flash_ok", "blue_ok", "tv_on", "music_started",
    "music_method", "mode", "beats_executed", "music_stopped", "tts_ok",
    "video_anchor",
)


class SceneMetrics:
    """
    Collecteur de metriques pour un lancement de scene.

    Usage:
        metrics = SceneMetrics(run_type="full", selection=[0,1,2,3,4,5])
        metrics.record_step("phase1", duration_s=3.0, success=True,
                            result={"latency_ms": 169})
        metrics.mark("first_visible_effect")
        metrics.finalize(success=True)   # sauvegarde + rotation 5 runs
    """

    def __init__(self, run_type: str, selection: list,
                 metrics_file: Path = METRICS_FILE):
        self.metrics_file = metrics_file
        self._start = time.perf_counter()
        self.run = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "run_type": run_type,
            "selection": selection,
            "success": None,
            "total_s": None,
            "time_to_first_effect_s": None,
            "steps": {},
            "markers": {},
        }

    def record_step(self, name: str, duration_s: float, success: bool,
                    result: Optional[dict] = None):
        """Enregistre une etape (phase ou sous-etape) avec ses extras."""
        step = {"duration_s": round(duration_s, 3), "success": success}
        if result:
            for key in _STEP_EXTRA_KEYS:
                if key in result:
                    value = result[key]
                    if isinstance(value, float):
                        value = round(value, 3)
                    step[key] = value
        self.run["steps"][name] = step

    def mark(self, name: str):
        """Pose un marqueur temporel (secondes depuis le debut du run)."""
        self.mark_at(name, time.perf_counter() - self._start)

    def mark_at(self, name: str, elapsed_s: float):
        """Pose un marqueur a un offset connu depuis le debut du run."""
        elapsed = round(elapsed_s, 3)
        self.run["markers"][name] = elapsed
        if name == "first_visible_effect":
            self.run["time_to_first_effect_s"] = elapsed

    def finalize(self, success: bool):
        """Clot le run et le persiste (rotation MAX_RUNS derniers)."""
        self.run["success"] = success
        self.run["total_s"] = round(time.perf_counter() - self._start, 3)
        try:
            runs = load_runs(self.metrics_file)
            runs.append(self.run)
            runs = runs[-MAX_RUNS:]
            self.metrics_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.metrics_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(runs, indent=2, ensure_ascii=False))
            tmp.replace(self.metrics_file)
        except Exception as e:
            # Les metriques ne doivent jamais faire echouer la scene
            logger.warning(f"[METRICS] Sauvegarde impossible: {e}")


def load_runs(metrics_file: Path = METRICS_FILE) -> list:
    """Charge les runs persistes (liste vide si absent/corrompu)."""
    try:
        data = json.loads(metrics_file.read_text())
        return data if isinstance(data, list) else []
    except FileNotFoundError:
        return []
    except Exception as e:
        logger.warning(f"[METRICS] Lecture impossible: {e}")
        return []


def format_comparison(runs: list) -> str:
    """
    Formate un tableau comparatif des derniers runs (plus recent a droite).

    Returns:
        Texte pret a imprimer
    """
    if not runs:
        return "Aucun run enregistre."

    lines = []
    header = f"{'Etape':<22}" + "".join(
        f"{r['timestamp'][5:16]:>15}" for r in runs
    )
    lines.append(header)
    lines.append("-" * len(header))

    step_names = []
    for r in runs:
        for name in r.get("steps", {}):
            if name not in step_names:
                step_names.append(name)

    for name in step_names:
        row = f"{name:<22}"
        for r in runs:
            step = r.get("steps", {}).get(name)
            if step is None:
                row += f"{'-':>15}"
            else:
                mark = "" if step.get("success") else " KO"
                row += f"{step['duration_s']:>12.2f}s{mark:<2}"
        lines.append(row)

    lines.append("-" * len(header))
    for label, key in (("time_to_first_effect", "time_to_first_effect_s"),
                       ("TOTAL", "total_s")):
        row = f"{label:<22}"
        for r in runs:
            value = r.get(key)
            row += f"{value:>13.2f}s " if value is not None else f"{'-':>15}"
        lines.append(row)

    row = f"{'succes':<22}"
    for r in runs:
        row += f"{'OUI' if r.get('success') else 'NON':>15}"
    lines.append(row)

    return "\n".join(lines)
