#!/usr/bin/env python3
"""Socle commun des benchmarks : releve du materiel et ecriture des resultats.

Un chiffre publie sans son contexte n'est pas verifiable. Chaque resultat
ecrit ici embarque donc la machine, les versions et la date : c'est ce qui
permet a quelqu'un d'autre de rejouer la mesure et de comparer.
"""

from __future__ import annotations

import json
import platform
import re
import subprocess
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BENCHMARKS = REPO / "benchmarks"
RESULTS = BENCHMARKS / "results"


def _commande(cmd: list[str]) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def gpu() -> dict:
    """Nom, VRAM et pilote du GPU NVIDIA, ou un dict vide sans GPU."""
    ligne = _commande(["nvidia-smi", "--query-gpu=name,memory.total,driver_version",
                       "--format=csv,noheader"])
    if not ligne:
        return {}
    parts = [p.strip() for p in ligne.splitlines()[0].split(",")]
    if len(parts) < 3:
        return {}
    return {"nom": parts[0], "vram": parts[1], "pilote": parts[2]}


def slug_gpu() -> str:
    """Identifiant de fichier, ex. 'rtx-3080-ti'. 'cpu' sans GPU."""
    nom = gpu().get("nom", "")
    if not nom:
        return "cpu"
    nom = re.sub(r"(?i)nvidia|geforce|rtx|gtx", " ", nom)
    slug = re.sub(r"[^a-z0-9]+", "-", nom.lower()).strip("-")
    return f"rtx-{slug}" if slug else "gpu"


def cpu() -> str:
    for ligne in Path("/proc/cpuinfo").read_text().splitlines():
        if ligne.startswith("model name"):
            return ligne.split(":", 1)[1].strip()
    return platform.processor() or "inconnu"


def ram_go() -> int:
    for ligne in Path("/proc/meminfo").read_text().splitlines():
        if ligne.startswith("MemTotal:"):
            return round(int(ligne.split()[1]) / 1024 / 1024)
    return 0


def versions() -> dict:
    ollama = _commande(["ollama", "--version"])
    commit = _commande(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"])
    return {
        "python": platform.python_version(),
        "ollama": ollama.split()[-1] if ollama else "absent",
        "lyra_commit": commit or "inconnu",
        "noyau": platform.release(),
    }


def modeles() -> dict:
    """Modeles reellement utilises par le pipeline V2 (config.yaml)."""
    try:
        import yaml
        cfg = yaml.safe_load((REPO / "config.yaml").read_text()) or {}
    except Exception:
        return {}
    m = cfg.get("models") or {}
    return {role: (m.get(role) or {}).get("name", "") for role in ("ephaistos", "lyra")}


def contexte() -> dict:
    """Tout ce qu'il faut pour rejouer la mesure ailleurs."""
    return {
        "date": date.today().isoformat(),
        "materiel": {"gpu": gpu(), "cpu": cpu(), "ram_go": ram_go()},
        "versions": versions(),
        "modeles": modeles(),
    }


def ecrire_resultat(mesure: str, donnees: dict, suffixe: str = "") -> Path:
    """Ecrit benchmarks/results/<date>-<gpu>[-<suffixe>]-<mesure>.json."""
    RESULTS.mkdir(parents=True, exist_ok=True)
    ctx = contexte()
    bout = f"-{suffixe}" if suffixe else ""
    chemin = RESULTS / f"{ctx['date']}-{slug_gpu()}{bout}-{mesure}.json"
    chemin.write_text(json.dumps({"mesure": mesure, **ctx, **donnees},
                                 indent=2, ensure_ascii=False) + "\n")
    return chemin
