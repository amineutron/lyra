"""Etat d'installation immuable, propage d'etape en etape."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .osdetect import Distro

DEFAULT_LYRA_REPO = "git@github.com:marouabah/lyra.git"


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

    def with_(self, **kwargs: Any) -> "InstallState":
        return replace(self, **kwargs)

    @property
    def venv_python(self) -> Path:
        return self.lyra_dir / ".venv" / "bin" / "python"

    @property
    def mcp_servers_dir(self) -> Path:
        return self.lyra_dir / "mcp-servers"
