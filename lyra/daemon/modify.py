"""
Lyra Daemon - Correction des arguments au prompt de confirmation ("m").

Logique pure (sans reseau) : analyse de la saisie "cle=valeur" et validation
par liste blanche. Le workflow (ask / re-confirmation) est dans actions.py.

Regles de securite :
- seuls les arguments DEJA proposes peuvent changer (pas de nouvelle cle, pas
  de changement d'outil) : le verdict de danger reste celui de l'outil propose ;
- les valeurs passent par une liste blanche de caracteres (aucun
  metacaractere shell) et gardent le type de la valeur d'origine ;
- le resultat n'est JAMAIS execute sans nouvelle confirmation.
"""

from __future__ import annotations

import re
import shlex
from typing import Any

MODIFY_ANSWERS = frozenset({"m", "mod", "modif", "modify", "modifier", "edit"})
MAX_MODIFY_ROUNDS = 3
MAX_VALUE_LEN = 200

# Liste blanche : debut alphanumerique, puis lettres, chiffres, espace et . _ , : @ / + = -
_VALUE_RE = re.compile(r"[\w][\w .,:@/+=-]*")


class ModifyError(ValueError):
    """Saisie de correction invalide (message affichable tel quel)."""


def is_modify_answer(answer: str) -> bool:
    return str(answer).strip().lower() in MODIFY_ANSWERS


def _validate_value(key: str, value: str) -> str:
    if not value or len(value) > MAX_VALUE_LEN:
        raise ModifyError(f"{key}: valeur vide ou trop longue (max {MAX_VALUE_LEN})")
    if not _VALUE_RE.fullmatch(value) or ".." in value:
        raise ModifyError(f"{key}: caracteres non autorises dans {value!r}")
    return value


def _coerce(key: str, value: str, original: Any) -> Any:
    """Garde le type de la valeur d'origine (bool avant int : bool est un int)."""
    value = _validate_value(key, value)
    if isinstance(original, bool):
        low = value.lower()
        if low in ("true", "oui", "1", "yes"):
            return True
        if low in ("false", "non", "0", "no"):
            return False
        raise ModifyError(f"{key}: booleen attendu (oui/non)")
    if isinstance(original, (int, float)):
        try:
            return type(original)(value)
        except ValueError:
            raise ModifyError(f"{key}: nombre attendu, recu {value!r}") from None
    if original is None or isinstance(original, str):
        return value
    raise ModifyError(f"{key}: argument complexe, non modifiable ici")


def parse_modification(text: str, current: dict) -> dict:
    """Applique "cle=valeur [cle2=valeur2]" a `current`, retourne un NOUVEAU dict.

    Une valeur nue (sans "=") n'est acceptee que si l'outil n'a qu'un argument.
    Leve ModifyError si la saisie est vide, mal formee ou hors liste blanche.
    """
    text = (text or "").strip()
    if not text:
        raise ModifyError("saisie vide")
    try:
        tokens = shlex.split(text)
    except ValueError as e:
        raise ModifyError(f"guillemets mal fermes: {e}") from None
    if not tokens:
        raise ModifyError("saisie vide")

    if not any("=" in t for t in tokens):
        if len(current) != 1:
            raise ModifyError("precise cle=valeur (arguments: "
                              + ", ".join(current) + ")")
        tokens = [f"{next(iter(current))}={' '.join(tokens)}"]

    updated = dict(current)
    for token in tokens:
        key, sep, value = token.partition("=")
        key = key.strip()
        if not sep or not key:
            raise ModifyError(f"format attendu cle=valeur, recu {token!r}")
        if key not in current:
            raise ModifyError(f"argument inconnu: {key} (possibles: "
                              + ", ".join(current) + ")")
        updated[key] = _coerce(key, value.strip(), current[key])
    return updated
