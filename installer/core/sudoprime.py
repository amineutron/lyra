"""Amorce du cache sudo avant le pipeline.

Les etapes du pipeline (paquets systeme, ecriture de /etc/sudoers.d/lyra)
tournent dans un thread arriere-plan pendant que Rich Live occupe le
terminal -- `sudo` n'a alors aucun moyen interactif de lire un mot de
passe : soit il attend indefiniment (`sudo tee` n'a pas de timeout), soit
il echoue apres son propre delai ("sudo: delai d'attente depasse durant
la lecture du mot de passe", observe apres ~300s). Amorcer `sudo -v` ICI,
avant que Live ne demarre, laisse l'utilisateur taper son mot de passe
normalement ; le cache sudo (timestamp, memes pid/tty) est ensuite valide
pour les appels sudo suivants du pipeline sans nouveau prompt.
"""
from __future__ import annotations

import subprocess


def ensure_sudo_cached(demo: bool = False) -> bool:
    """Renvoie True si le cache sudo est pret (ou en mode demo, ou skip
    d'emblee car deja passwordless). False si l'utilisateur echoue/annule."""
    if demo:
        return True
    # sudo -n -v : deja passwordless / deja en cache -> rien a demander.
    if subprocess.run(["sudo", "-n", "-v"],
                      capture_output=True).returncode == 0:
        return True
    return subprocess.run(["sudo", "-v"]).returncode == 0
