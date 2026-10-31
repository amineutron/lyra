"""Fichiers des taches de fond (.log, .pid, .progress, .done) dans un dossier prive.

Ils vivaient dans /tmp sous un nom previsible (lyra_task_<date>_<n>) et etaient crees
lisibles par tous : un autre compte de la machine lisait la sortie des scripts (noms de
VM, chemins de sauvegarde) et pouvait deposer d'avance un faux .done ou un .pid.

Dossier : LYRA_TASK_DIR, sinon $XDG_RUNTIME_DIR/lyra/tasks (tmpfs propre a
l'utilisateur), sinon ~/.lyra/tasks ; toujours en 0700. Le demon et
scripts/async_mcp_wrapper.py (son enfant, meme environnement) calculent le meme chemin.

Ecriture : `task_file` (cree et controle le dossier). Lecture : `task_file_read`, qui
retombe en lecture seule sur l'emplacement enregistre (pid_file du registre) puis sur
l'ancien /tmp pour les taches lancees avant la migration, sans jamais rien creer.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Mapping, Optional

LEGACY_DIR = Path("/tmp")  # ancien emplacement : lecture seule, taches deja en cours


def _dossier(env: Mapping[str, str]) -> Path:
    force = (env.get("LYRA_TASK_DIR") or "").strip()
    if force:
        return Path(force).expanduser()
    if (env.get("XDG_RUNTIME_DIR") or "").strip():
        return Path(env["XDG_RUNTIME_DIR"]) / "lyra" / "tasks"
    return Path.home() / ".lyra" / "tasks"


def task_dir(env: Optional[Mapping[str, str]] = None, creer: bool = True) -> Path:
    """Dossier des taches. Avec `creer`, le cree en 0700 et refuse un dossier qui n'est pas
    a l'utilisateur courant ou qui est un lien symbolique ; un mode trop ouvert est corrige
    (chmod uniquement si le mode differe)."""
    env = os.environ if env is None else env
    d = _dossier(env)
    if not creer:
        return d
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    st = os.lstat(d)
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        raise PermissionError(f"dossier des taches refuse (lien symbolique ou non dossier) : {d}")
    if st.st_uid != os.geteuid():
        raise PermissionError(f"dossier des taches refuse (autre proprietaire) : {d}")
    if stat.S_IMODE(st.st_mode) != 0o700:
        os.chmod(d, 0o700)
    return d


def _verifie_id(task_id: str) -> None:
    if not task_id or "/" in task_id or task_id.startswith("."):
        raise ValueError(f"identifiant de tache invalide : {task_id!r}")


def task_file(task_id: str, ext: str, env: Optional[Mapping[str, str]] = None) -> str:
    """Chemin d'ecriture du fichier `ext` (log, pid, progress, done) de la tache."""
    _verifie_id(task_id)
    return str(task_dir(env) / f"lyra_task_{task_id}.{ext}")


def _lisible_sans_risque(p: Path) -> bool:
    """Fichier regulier (pas de lien symbolique) appartenant a l'utilisateur courant."""
    try:
        st = os.lstat(p)
    except OSError:
        return False
    return stat.S_ISREG(st.st_mode) and st.st_uid == os.geteuid()


def task_file_read(task_id: str, ext: str, pid_file: Optional[str] = None,
                   env: Optional[Mapping[str, str]] = None,
                   legacy_dir: Optional[Path] = None) -> str:
    """Chemin de LECTURE du fichier `ext` : dossier courant s'il y existe, sinon le dossier
    du `pid_file` enregistre, sinon l'ancien /tmp (fichiers a nous, non-liens). A defaut,
    le chemin courant (inexistant). Ne cree rien et n'ecrit jamais dans /tmp."""
    _verifie_id(task_id)
    env = os.environ if env is None else env
    nom = f"lyra_task_{task_id}.{ext}"
    courant = _dossier(env) / nom
    if os.path.lexists(courant):
        return str(courant)
    candidats = []
    if pid_file:
        candidats.append(Path(pid_file).parent / nom)
    candidats.append((legacy_dir or LEGACY_DIR) / nom)
    for c in candidats:
        if _lisible_sans_risque(c):
            return str(c)
    return str(courant)
