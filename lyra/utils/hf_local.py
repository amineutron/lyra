"""Chargement des modeles Hugging Face : cache local d'abord, reseau seulement s'il manque (lyra#25).

Sans `local_files_only`, sentence-transformers et faster-whisper interrogent
huggingface.co a CHAQUE chargement, meme modele deja en cache (requetes HEAD
visibles dans le journal du demon a chaque demarrage). Sur une machine sans
Internet, cela coute des timeouts ; sur un reseau d'entreprise, une connexion
sortante que personne n'a demandee.

Ordre : cache local ; s'il manque, telechargement unique, sauf en mode hors
ligne force (`LYRA_OFFLINE=1` ou `HF_HUB_OFFLINE=1`) ou l'erreur dit quoi faire.
"""

from __future__ import annotations

import logging
import os
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

_VRAI = {"1", "true", "yes", "on", "oui"}


def hors_ligne_force() -> bool:
    """Vrai si l'utilisateur interdit tout telechargement de modele."""
    return any(os.environ.get(v, "").strip().lower() in _VRAI for v in ("LYRA_OFFLINE", "HF_HUB_OFFLINE"))


def charger_local_puis_reseau(charger: Callable[..., T], nom: str) -> T:
    """Appelle `charger(local_files_only=True)`, puis `charger(local_files_only=False)` si le cache manque."""
    try:
        return charger(local_files_only=True)
    except Exception as exc:  # OSError, LocalEntryNotFoundError, ValueError selon la bibliotheque
        if hors_ligne_force():
            raise RuntimeError(
                f"modele {nom!r} absent du cache local et mode hors ligne actif "
                "(LYRA_OFFLINE / HF_HUB_OFFLINE) : le telecharger une fois avec le reseau, "
                "ou installer depuis un bundle hors ligne"
            ) from exc
        logger.info("modele %s absent du cache local (%s) : telechargement", nom, type(exc).__name__)
        return charger(local_files_only=False)
