"""Emplacement des scripts systeme (vm-controller, backup-manager, kvm).

Les scripts sont embarques dans le depot fedora-agents (mcp-servers/
fedora-agents/scripts) et installes par l'installeur en copie root:root
dans /usr/local/lib/lyra/scripts. Seule cette copie systeme peut etre
referencee par des regles sudoers NOPASSWD : un script dans $HOME est
inscriptible par l'utilisateur, donc par n'importe quel processus de son
uid, ce qui equivaut a un NOPASSWD: ALL.

Ordre de resolution de scripts_dir() :
  1. variable d'environnement LYRA_SCRIPTS_DIR
  2. cle `paths.scripts` de config.yaml
  3. DEFAULT_SCRIPTS_DIR
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping, Optional

import yaml

DEFAULT_SCRIPTS_DIR = "/usr/local/lib/lyra/scripts"
ENV_VAR = "LYRA_SCRIPTS_DIR"

# Racine du depot lyra (lyra/core/paths.py -> ../..)
LYRA_ROOT = Path(__file__).resolve().parents[2]

# Chemin par defaut du serveur MCP fedora-agents (clone par l'installeur)
DEFAULT_FEDORA_MCP_SERVER = LYRA_ROOT / "mcp-servers" / "fedora-agents" / "dist" / "index.js"


def scripts_dir(config: Optional[Mapping[str, Any]] = None,
                env: Optional[Mapping[str, str]] = None) -> Path:
    """Racine des scripts systeme (logique pure, testable)."""
    env = os.environ if env is None else env
    from_env = (env.get(ENV_VAR) or "").strip()
    if from_env:
        return Path(from_env).expanduser()
    paths = (config or {}).get("paths") or {}
    from_cfg = (paths.get("scripts") or "").strip() if isinstance(paths, Mapping) else ""
    if from_cfg:
        return Path(from_cfg).expanduser()
    return Path(DEFAULT_SCRIPTS_DIR)


def load_config(path: Optional[Path] = None) -> dict:
    """Lit config.yaml (racine du depot par defaut). {} si absent/illisible."""
    path = path or (LYRA_ROOT / "config.yaml")
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, yaml.YAMLError):
        return {}


def scripts_dir_from_config(config_path: Optional[Path] = None) -> Path:
    """scripts_dir() alimente par config.yaml + environnement."""
    return scripts_dir(load_config(config_path))


def vm_controller_dir(base: Optional[Path] = None) -> Path:
    return (base or scripts_dir_from_config()) / "agents" / "vm-controller"


def backup_manager_dir(base: Optional[Path] = None) -> Path:
    return (base or scripts_dir_from_config()) / "agents" / "backup-manager"


def kvm_dir(base: Optional[Path] = None) -> Path:
    return (base or scripts_dir_from_config()) / "kvm"
