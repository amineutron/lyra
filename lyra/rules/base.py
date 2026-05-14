"""Lyra Rules - Utilitaires partages."""

import unicodedata


def normalize(query: str) -> str:
    """Normalise une requete: minuscules + suppression diacritiques."""
    q = unicodedata.normalize('NFD', query.lower())
    return ''.join(c for c in q if unicodedata.category(c) != 'Mn')


def make(tool: str, arguments: dict, reasoning: str, confidence: float = 0.92,
         missing_args: list | None = None):
    """Cree un EphaistosAnalysis pour une regle (import lazy pour eviter circular imports)."""
    from ..models._analysis import EphaistosAnalysis
    return EphaistosAnalysis(
        tool=tool,
        arguments=arguments,
        missing_args=missing_args or [],
        confidence=confidence,
        reasoning=reasoning,
        raw_response=""
    )
