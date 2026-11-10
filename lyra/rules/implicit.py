"""Regles de l'intention implicite : "ok vasy" reprend la derniere action proposee.

Deux fonctions pures, sans LLM et sans etat (l'etat vit dans la session) :

- is_affirmation(query) : la phrase est-elle UNIQUEMENT un assentiment
  ("ok vasy", "oui lance ca", "go", "fais-le") ? Correspondance complete :
  tout mot en plus ("ok merci", "oui mais pas la tele", "vas-y lance la scene
  soiree") rend la phrase non ambigue pour les regles normales, qui la traitent.
- extract_proposal(reply) : l'action unique que la reponse de Lyra propose
  ("je peux lancer la scene soiree", "tu veux que j'eteigne la tele ?").

Ce module ne decide jamais d'executer : l'appelant rejoue l'action par le flux
normal de confirmation (voir lyra/daemon/implicit.py).
"""

import re

from .base import normalize

# Mots d'assentiment et verbes d'execution acceptes (apres normalisation).
_ASSENT = r"(?:ok|okay|oui|ouais|yes|yep|d accord|dac|ok d accord|carrement|bien sur)"
_GO = r"(?:vas y|vasy|allez|go|fais le|fais ca|fait le|lance|lance le|lance ca|" \
      r"envoie|envoie ca|execute|execute le|execute ca|fonce|c est bon)"
_AFFIRMATION = re.compile(rf"^(?:{_ASSENT}(?:\s+{_GO})?|{_GO})(?:\s+s il te plait|\s+stp)?$")

# Marqueurs d'une proposition de Lyra ; capture la clause d'action qui suit.
_PROPOSAL = re.compile(
    r"(?:je\s+peux(?:\s+aussi)?|je\s+pourrais|je\s+te\s+propose\s+de|"
    r"veux[\s-]+tu\s+que\s+je|tu\s+veux\s+que\s+je|souhaites[\s-]+tu\s+que\s+je|"
    r"voulez[\s-]+vous\s+que\s+je|si\s+tu\s+veux,?\s+je(?:\s+peux)?)\s+([^?.!\n]+)",
    re.IGNORECASE,
)
_COMPOUND = re.compile(r"\b(?:et|puis|ensuite|apres|ou)\b")
# Fin de clause : politesse ou virgule qui n'appartient pas a l'argument
# ("lancer la scene soiree, si tu veux" ne doit pas donner la scene "soiree si tu veux").
_TAIL = re.compile(r"(?:,|\bsi tu (?:veux|le souhaites|le veux)\b|\bsi tu en as envie\b|"
                   r"\bmaintenant\b|\btout de suite\b|\bsi besoin\b).*$", re.IGNORECASE)
_MAX_REPLY = 1500


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]|_", " ", normalize(text))).strip()


def is_affirmation(query: str) -> bool:
    """True si la phrase entiere est un assentiment bref, rien d'autre."""
    if not isinstance(query, str) or not query.strip() or len(query) > 60:
        return False
    return _AFFIRMATION.match(_clean(query)) is not None


def extract_proposal(reply: str):
    """EphaistosAnalysis de l'unique action proposee par `reply`, sinon None.

    Une reponse qui propose plusieurs actions differentes, une clause composee
    ("... et ...") ou une clause qu'aucune regle ne reconnait ne donne rien :
    on ne devine pas ce que "ok" voudrait dire.
    """
    from . import detect
    if not isinstance(reply, str) or not reply.strip():
        return None
    found = {}
    for match in _PROPOSAL.finditer(reply[:_MAX_REPLY]):
        clause = _TAIL.sub("", match.group(1)).strip()
        if _COMPOUND.search(normalize(clause)):
            return None
        analysis = detect(clause)
        if analysis is not None and analysis.tool:
            found[(analysis.tool, repr(sorted(analysis.arguments.items())))] = analysis
    return next(iter(found.values())) if len(found) == 1 else None
