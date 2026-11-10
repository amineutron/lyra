"""
Lyra Client - Logique pure du mode vocal via le demon.

Aucun acces audio ni reseau ici (testable en table) :
- texte a prononcer pour un message "output" du demon
- interpretation d'une reponse parlee a une confirmation

Regle de securite : une reponse ambigue, vide ou inintelligible ne devient
JAMAIS une confirmation. Le demon traite une reponse vide comme "oui" pour
une action non dangereuse : le client vocal n'envoie donc jamais "". La
decision finale reste au demon (une action dangereuse exige "o"/"oui").
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

from lyra.client.speech_fr import humanize_for_speech

MAX_SPOKEN_CHARS = 300

# Sorties lues a voix haute (les autres restent a l'ecran seulement)
SPOKEN_KINDS = ("lyra", "lyra_tag", "tool_result", "error")

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_PROMPT_SUFFIX_RE = re.compile(r"\s*\[[oOyY]/[nN](/[mM])?\]\s*$")
_TAG_RE = re.compile(r"^\s*\[[+\-!?*]\]\s*")

YES_WORDS = frozenset({"oui", "ouais", "yes", "ok", "okay", "d'accord", "daccord",
                       "vas-y", "vasy", "confirme", "confirmer", "go", "yep"})
# Pour une action dangereuse : confirmation explicite uniquement
DANGER_YES_WORDS = frozenset({"oui", "confirme", "confirmer", "yes"})
NO_WORDS = frozenset({"non", "no", "annule", "annuler", "stop", "laisse", "nope",
                      "jamais", "pas"})
MODIFY_WORDS = frozenset({"modifier", "modifie", "corriger", "corrige"})

ANSWER_YES = "oui"
ANSWER_NO = "non"
ANSWER_MODIFY = "m"


def _normalize(text: str) -> list[str]:
    """Minuscules, sans accents ni ponctuation, decoupe en mots."""
    lowered = unicodedata.normalize("NFKD", text.lower())
    stripped = "".join(c for c in lowered if not unicodedata.combining(c))
    return re.findall(r"[a-z']+(?:-[a-z]+)?", stripped)


def clean_for_speech(text: str, limit: int = MAX_SPOKEN_CHARS) -> str:
    """Retire codes ANSI, marqueurs [+]/[!] et suffixe [O/n] ; tronque."""
    cleaned = _ANSI_RE.sub("", text or "")
    cleaned = _TAG_RE.sub("", cleaned.strip())
    cleaned = _PROMPT_SUFFIX_RE.sub("", cleaned)
    cleaned = " ".join(cleaned.split())
    if len(cleaned) > limit:
        cleaned = cleaned[:limit].rsplit(" ", 1)[0].rstrip(",;:") + "..."
    return cleaned


def spoken_text(message: dict) -> Optional[str]:
    """Texte a prononcer pour un message {"type": "output"}, ou None."""
    if message.get("type") != "output":
        return None
    if message.get("kind") not in SPOKEN_KINDS:
        return None
    text = humanize_for_speech(str(message.get("text", "")))
    return text or None


def interpret_confirmation(transcript: str, danger: bool = False) -> Optional[str]:
    """Reponse parlee -> valeur a envoyer au demon, ou None si indecidable.

    None signifie "redemander" (ou refuser apres plusieurs essais) : jamais
    une confirmation implicite.
    """
    words = _normalize(transcript or "")
    if not words:
        return None
    wordset = set(words)
    if wordset & NO_WORDS:
        return ANSWER_NO  # une negation l'emporte toujours ("pas oui", "non annule")
    if wordset & MODIFY_WORDS:
        return ANSWER_MODIFY
    yes = DANGER_YES_WORDS if danger else YES_WORDS
    if wordset & yes:
        return ANSWER_YES
    return None
