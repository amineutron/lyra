"""Regles de detection pour la scene Iron Man."""

import re
from .base import normalize, make

# Triggers exacts (normalises: minuscules, sans accents)
_TRIGGERS_EXACT = [
    "je suis iron man",
    "je suis ironman",
    "je suis tony stark",
    "je suis tony",
    "mode iron man",
    "scene iron man",
    "lance iron man",
    "demarre iron man",
    "active iron man",
]


def detect(query: str):
    q = normalize(query)

    # Correspondances exactes (substring)
    for trigger in _TRIGGERS_EXACT:
        if trigger in q:
            return make("ironman.run_scene", {}, f"rule: trigger '{trigger}'", 0.98)

    # Patterns flexibles: "lance/active/demarre la scene iron man"
    if re.search(r'\b(?:lance[rz]?|demarr[ea][rz]?|active[rz]?|execute[rz]?)\b', q) \
            and re.search(r'\biron\b', q) \
            and re.search(r'\b(?:man|scene)\b', q):
        return make("ironman.run_scene", {}, "rule: verbe + iron + man/scene", 0.96)

    return None
