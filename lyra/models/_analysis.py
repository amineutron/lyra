"""EphaistosAnalysis - Dataclass resultat d'analyse, sans dependances lourdes.

Fichier isole pour eviter les imports circulaires entre rules/ et models/.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class EphaistosAnalysis:
    """Resultat d'analyse EPHAISTOS."""
    tool: Optional[str]
    arguments: dict
    missing_args: list[str]
    confidence: float
    reasoning: str
    raw_response: str

    @property
    def is_ready(self) -> bool:
        """Verifie si l'analyse est prete pour execution."""
        return self.tool is not None and len(self.missing_args) == 0

    @property
    def needs_clarification(self) -> bool:
        """Verifie si des clarifications sont necessaires."""
        return self.tool is not None and len(self.missing_args) > 0

    @property
    def no_match(self) -> bool:
        """Verifie si aucun outil ne correspond."""
        return self.tool is None
