"""Etat d'installation immuable, propage d'etape en etape."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .osdetect import Distro

DEFAULT_LYRA_REPO = "git@github.com:amineutron/lyra.git"


# Nom d'hote ou IPv4 (lettres, chiffres, points, tirets, sans tiret initial), ou IPv6
# entre crochets. Pas de port : l'installeur ajoute toujours :11434.
_HOTE_OLLAMA = re.compile(r"^(?:[A-Za-z0-9](?:[A-Za-z0-9.-]{0,252})|\[[0-9A-Fa-f:.]{2,45}\])$")


def valider_hote_ollama(hote: str) -> str:
    """Rend `hote` s'il est un nom d'hote ou une adresse ; leve ValueError sinon.

    La valeur finit dans ~/.bashrc (export OLLAMA_HOST=...), config.yaml et
    l'environnement de `ollama pull` : rien d'autre qu'un hote ne doit passer.
    """
    if hote and not _HOTE_OLLAMA.fullmatch(hote):
        raise ValueError(f"hote Ollama invalide : {hote!r} (attendu : nom d'hote ou adresse IP, sans port)")
    return hote


def hote_ollama_arg(valeur: str) -> str:
    """Type argparse de --ollama-host : erreur de ligne de commande lisible, pas une trace."""
    import argparse
    try:
        return valider_hote_ollama(valeur)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None


@dataclass(frozen=True)
class InstallState:
    distro: Distro
    lyra_dir: Path                      # racine du clone lyra
    repo_url: str = DEFAULT_LYRA_REPO
    selected_mcps: tuple[str, ...] = ()  # ids du catalogue coches
    device_config: dict = field(default_factory=dict)   # {mcp_id: {champ: valeur}}
    secrets: dict = field(default_factory=dict)          # {section: {cle: valeur}} -> secrets.yaml
    ollama_host: str = ""               # vide = install locale d'Ollama
    skip_models: bool = False
    demo: bool = False                  # simulation : aucune commande reelle
    install_smoke_timer: bool = False
    # MCPs optionnels dont l'etape a echoue (device manquant, paquet casse...)
    # -> ecrit dans config.yaml, lu par lyra/client au demarrage pour rappel.
    incomplete_mcps: list = field(default_factory=list)

    def __post_init__(self) -> None:
        valider_hote_ollama(self.ollama_host)

    def with_(self, **kwargs: Any) -> "InstallState":
        return replace(self, **kwargs)

    @property
    def venv_python(self) -> Path:
        return self.lyra_dir / ".venv" / "bin" / "python"

    @property
    def mcp_servers_dir(self) -> Path:
        return self.lyra_dir / "mcp-servers"
