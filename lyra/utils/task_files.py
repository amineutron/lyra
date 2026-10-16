"""Fichiers des taches de fond (.log, .pid, .progress, .done) dans un dossier prive.

Ils vivaient dans /tmp sous un nom previsible (lyra_task_<date>_<n>) et etaient crees
lisibles par tous : un autre compte de la machine lisait la sortie des scripts (noms de
VM, chemins de sauvegarde) et pouvait deposer d'avance un faux .done ou un .pid.

Dossier : LYRA_TASK_DIR, sinon $XDG_RUNTIME_DIR/lyra/tasks (tmpfs propre a
l'utilisateur), sinon ~/.lyra/tasks ; toujours remis en 0700. Le demon et
scripts/async_mcp_wrapper.py (son enfant, meme environnement) calculent le meme chemin.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping, Optional


def task_dir(env: Optional[Mapping[str, str]] = None, creer: bool = True) -> Path:
    env = os.environ if env is None else env
    force = (env.get("LYRA_TASK_DIR") or "").strip()
    if force:
        d = Path(force).expanduser()
    elif (env.get("XDG_RUNTIME_DIR") or "").strip():
        d = Path(env["XDG_RUNTIME_DIR"]) / "lyra" / "tasks"
    else:
        d = Path.home() / ".lyra" / "tasks"
    if creer:
        d.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(d, 0o700)
    return d


def task_file(task_id: str, ext: str, env: Optional[Mapping[str, str]] = None) -> str:
    """Chemin du fichier `ext` (log, pid, progress, done) de la tache `task_id`."""
    if not task_id or "/" in task_id or task_id.startswith("."):
        raise ValueError(f"identifiant de tache invalide : {task_id!r}")
    return str(task_dir(env) / f"lyra_task_{task_id}.{ext}")
