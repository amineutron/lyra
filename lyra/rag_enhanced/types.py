"""
Types communs pour le système RAG Enhanced.

Définit les TypedDict et Enums utilisés à travers les modules RAG Enhanced.
"""

from typing import TypedDict, Literal, Optional
from enum import Enum


class ConfidenceLevel(Enum):
    """Niveaux de confiance RAG."""
    HIGH = "high"      # >0.85
    MEDIUM = "medium"  # 0.60-0.85
    LOW = "low"        # <0.60


class CascadeAction(Enum):
    """Actions de cascade selon le niveau de confiance."""
    EXECUTE = "execute"      # >0.85 - Exécution directe
    PROPOSE = "propose"      # 0.60-0.85 - Proposer options + contexte
    FALLBACK = "fallback"    # <0.60 - Fallback LYRA conversation


class QueryContext(TypedDict, total=False):
    """Contexte d'une requête utilisateur.

    Attributes:
        query: Requête originale de l'utilisateur
        session_id: ID de session pour tracking
        rag_score: Score de confiance RAG (0-1)
        last_mcp: Dernier outil MCP utilisé dans la session
        frequent_mcp: Outil MCP le plus fréquent sur fenêtre
    """
    query: str
    session_id: str
    rag_score: float
    last_mcp: Optional[str]
    frequent_mcp: Optional[str]


class RAGResult(TypedDict):
    """Résultat RAG enrichi.

    Attributes:
        tool_name: Nom de l'outil MCP identifié
        confidence: Score de confiance (0-1)
        source: Collection source ("registry", "capabilities", "parameters")
        metadata: Métadonnées additionnelles du résultat
    """
    tool_name: str
    confidence: float
    source: Literal["registry", "capabilities", "parameters"]
    metadata: dict


class FeedbackEntry(TypedDict):
    """Entrée de feedback pour apprentissage.

    Attributes:
        query: Requête utilisateur
        tool_name: Outil MCP identifié
        rag_score: Score RAG
        success: True si bon outil, False sinon
        timestamp: Timestamp de l'entrée
    """
    query: str
    tool_name: str
    rag_score: float
    success: bool
    timestamp: int
