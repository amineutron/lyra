"""
Confidence Cascader pour RAG Enhanced.

Décide de l'action à prendre selon le score de confiance RAG.

SESSION 6 (P5)
"""

import logging
import time
from typing import Optional

from .types import CascadeAction
from .constants import CONFIDENCE_HIGH, CONFIDENCE_MEDIUM

logger = logging.getLogger(__name__)


class ConfidenceCascader:
    """
    Cascadeur de confiance pour décider de l'action selon score RAG.

    3 niveaux de confiance (M2):
        HIGH (>0.80): EXECUTE - confirmation courte et directe
        MEDIUM (0.50-0.80): PROPOSE - verification etat MCP + confirmation serveur
        LOW (<0.50): FALLBACK - LYRA exprime incertitude, demande clarification

    Exemples:
        >>> cascader = ConfidenceCascader()
        >>> action = cascader.cascade(0.90, [{'tool_name': 'vm_start', 'score': 0.90}])
        >>> print(action)  # CascadeAction.EXECUTE
    """

    def __init__(self):
        """Initialise le cascadeur."""
        self._metrics = {
            'execute_count': 0,
            'propose_count': 0,
            'fallback_count': 0,
            'total_latency_ms': 0.0,
            'cascade_count': 0
        }

    def cascade(
        self,
        rag_score: float,
        rag_results: list[dict]
    ) -> CascadeAction:
        """
        Décide l'action selon le score RAG.

        Args:
            rag_score: Score de confiance RAG (0-1)
            rag_results: Liste résultats RAG triés par score DESC
                        Format: [{'tool_name': str, 'score': float}, ...]

        Returns:
            CascadeAction: Action recommandée (EXECUTE/PROPOSE/FALLBACK)

        Règles (M2 - nouveaux seuils):
            - >0.80: EXECUTE - confirmation courte
            - 0.50-0.80: PROPOSE - vérif état + confirmation serveur
            - <0.50: FALLBACK - incertitude LYRA
        """
        start_time = time.time()

        # Edge case: résultats vides
        if not rag_results:
            logger.warning("Résultats RAG vides, fallback LYRA")
            action = CascadeAction.FALLBACK
        else:
            # Décision basée sur score (seuils M2)
            if rag_score > CONFIDENCE_HIGH:
                action = CascadeAction.EXECUTE
            elif rag_score >= CONFIDENCE_MEDIUM:
                action = CascadeAction.PROPOSE
            else:
                action = CascadeAction.FALLBACK

        # Tracking métriques
        self._metrics['cascade_count'] += 1
        self._metrics['total_latency_ms'] += (time.time() - start_time) * 1000

        if action == CascadeAction.EXECUTE:
            self._metrics['execute_count'] += 1
        elif action == CascadeAction.PROPOSE:
            self._metrics['propose_count'] += 1
        else:
            self._metrics['fallback_count'] += 1

        logger.debug(
            f"Cascade: score={rag_score:.2f} → {action.value} "
            f"(exec={self._metrics['execute_count']}, "
            f"prop={self._metrics['propose_count']}, "
            f"fall={self._metrics['fallback_count']})"
        )

        return action

    def cascade_detailed(
        self,
        rag_score: float,
        rag_results: list[dict]
    ) -> dict:
        """
        Décide l'action avec détails sur injection contexte et niveau de confiance.

        Args:
            rag_score: Score de confiance RAG (0-1)
            rag_results: Liste résultats RAG triés par score DESC

        Returns:
            dict: {
                'action': CascadeAction,
                'confidence_level': str ("high"/"medium"/"low"),
                'should_inject_context': bool,
                'gap': float | None (écart entre top 2 si >1 résultat)
            }
        """
        action = self.cascade(rag_score, rag_results)

        # Niveau de confiance lisible (pour M1 verbose et M2 confirmations)
        if rag_score > CONFIDENCE_HIGH:
            confidence_level = "high"
        elif rag_score >= CONFIDENCE_MEDIUM:
            confidence_level = "medium"
        else:
            confidence_level = "low"

        # Calcul gap si MEDIUM + au moins 2 résultats
        should_inject_context = False
        gap = None

        if action == CascadeAction.PROPOSE and len(rag_results) >= 2:
            gap = round(rag_results[0]['score'] - rag_results[1]['score'], 3)
            should_inject_context = gap < 0.10

            if should_inject_context:
                logger.info(
                    f"Gap faible ({gap:.3f} < 0.10) → "
                    f"injection contexte recommandée"
                )

        return {
            'action': action,
            'confidence_level': confidence_level,
            'should_inject_context': should_inject_context,
            'gap': gap
        }

    def get_metrics(self) -> dict:
        """
        Retourne métriques du cascadeur.

        Returns:
            dict: {
                'execute_count': int,
                'propose_count': int,
                'fallback_count': int,
                'latency_ms': float (moyenne),
                'total_cascades': int
            }
        """
        avg_latency = (
            self._metrics['total_latency_ms'] / self._metrics['cascade_count']
            if self._metrics['cascade_count'] > 0
            else 0.0
        )

        return {
            'execute_count': self._metrics['execute_count'],
            'propose_count': self._metrics['propose_count'],
            'fallback_count': self._metrics['fallback_count'],
            'latency_ms': round(avg_latency, 3),
            'total_cascades': self._metrics['cascade_count']
        }


# Instance singleton (lazy-loaded)
_instance: Optional[ConfidenceCascader] = None


def get_confidence_cascader() -> ConfidenceCascader:
    """
    Retourne instance singleton du ConfidenceCascader.

    Returns:
        ConfidenceCascader: Instance unique
    """
    global _instance
    if _instance is None:
        _instance = ConfidenceCascader()
    return _instance
