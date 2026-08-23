"""Palette neutroncore et chargement des mascottes.

Seule source de couleurs du frontal TUI : les modules de rendu importent
ces constantes au lieu de coder des styles rich en dur.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Palette portee de neutroncore
GOLD = "#f6c177"    # accent principal (titres, etapes faites)
ROSE = "#eb6f92"    # etape en cours, spinner
OK = "#82d69c"      # succes
WARN = "#f0b45e"    # avertissement
CRIT = "#ff5c74"    # erreur
MUTED = "#9c8ea6"   # texte secondaire

# Styles rich derives
TITLE = f"bold {GOLD}"
TITLE_DIM = f"dim {GOLD}"
RUN = f"bold {ROSE}"
GOOD = f"bold {OK}"
BAD = f"bold {CRIT}"
DIM = f"dim {MUTED}"
TEXT = "bold white"

# Codes couleur des mascottes (champ "c" de mascots.json) -> palette
MASCOT_COLORS: dict[str, str] = {
    "o": GOLD,
    "g": OK,
    "p": ROSE,
    "b": "#7fb2e0",
}

SPINNER_FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

MASCOTS_PATH = Path(__file__).resolve().parent.parent / "assets" / "mascots.json"


def load_mascots(path: Path = MASCOTS_PATH) -> dict[str, list[dict[str, Any]]]:
    """Charge installer/assets/mascots.json ({"fast": [...], "slow": [...]}).

    Retourne un dict vide par famille si le fichier est absent ou invalide :
    l'installeur ne doit jamais planter pour une mascotte.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"fast": [], "slow": []}
    if not isinstance(data, dict):
        return {"fast": [], "slow": []}
    return {
        "fast": list(data.get("fast") or []),
        "slow": list(data.get("slow") or []),
    }


def mascot_color(code: str) -> str:
    """Couleur rich pour un code couleur de mascotte."""
    return MASCOT_COLORS.get(code, MUTED)
