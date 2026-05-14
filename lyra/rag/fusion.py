"""
Lyra RAG - RRF Fusion.

Reciprocal Rank Fusion pour combiner les resultats
de recherche semantique et keyword.
"""

from dataclasses import dataclass
from typing import Union

from .semantic_retriever import SemanticResult
from .keyword_retriever import KeywordResult


@dataclass
class FusedResult:
    """Resultat fusionne."""
    document: str
    metadata: dict
    rrf_score: float
    id: str
    semantic_rank: int | None = None
    keyword_rank: int | None = None


class RRFFusion:
    """Reciprocal Rank Fusion (RRF).

    Combine les rankings de plusieurs retrievers en utilisant
    la formule: score = sum(1 / (k + rank))

    Ou k est une constante (typiquement 60) qui reduit l'impact
    des differences de rang aux positions elevees.

    Reference:
    Cormack, G. V., et al. (2009). "Reciprocal rank fusion outperforms
    condorcet and individual rank learning methods."
    """

    def __init__(self, k: int = 60):
        """Initialise le fusionneur.

        Args:
            k: Constante RRF (defaut: 60)
        """
        self.k = k

    def fuse(
        self,
        semantic_results: list[SemanticResult],
        keyword_results: list[KeywordResult],
        top_k: int = 3
    ) -> list[FusedResult]:
        """Fusionne les resultats des deux retrievers.

        Args:
            semantic_results: Resultats de recherche semantique
            keyword_results: Resultats de recherche keyword
            top_k: Nombre de resultats a retourner

        Returns:
            Liste de FusedResult ordonnee par score RRF
        """
        # Dict pour accumuler les scores par document ID
        scores: dict[str, dict] = {}

        # Ajouter les scores semantiques
        for rank, result in enumerate(semantic_results, start=1):
            doc_id = result.id
            rrf_score = 1.0 / (self.k + rank)

            if doc_id not in scores:
                scores[doc_id] = {
                    "document": result.document,
                    "metadata": result.metadata,
                    "rrf_score": 0.0,
                    "semantic_rank": None,
                    "keyword_rank": None
                }

            scores[doc_id]["rrf_score"] += rrf_score
            scores[doc_id]["semantic_rank"] = rank

        # Ajouter les scores keyword
        for rank, result in enumerate(keyword_results, start=1):
            doc_id = result.id
            rrf_score = 1.0 / (self.k + rank)

            if doc_id not in scores:
                scores[doc_id] = {
                    "document": result.document,
                    "metadata": result.metadata,
                    "rrf_score": 0.0,
                    "semantic_rank": None,
                    "keyword_rank": None
                }

            scores[doc_id]["rrf_score"] += rrf_score
            scores[doc_id]["keyword_rank"] = rank

        # Trier par score RRF decroissant
        sorted_ids = sorted(
            scores.keys(),
            key=lambda x: scores[x]["rrf_score"],
            reverse=True
        )[:top_k]

        # Construire les resultats
        results = []
        for doc_id in sorted_ids:
            data = scores[doc_id]
            results.append(FusedResult(
                document=data["document"],
                metadata=data["metadata"],
                rrf_score=data["rrf_score"],
                id=doc_id,
                semantic_rank=data["semantic_rank"],
                keyword_rank=data["keyword_rank"]
            ))

        return results

    def explain(self, result: FusedResult) -> str:
        """Explique le score d'un resultat.

        Args:
            result: Resultat fusionne

        Returns:
            Explication textuelle du scoring
        """
        parts = [f"RRF Score: {result.rrf_score:.4f}"]

        if result.semantic_rank is not None:
            semantic_contrib = 1.0 / (self.k + result.semantic_rank)
            parts.append(f"  - Semantic rank #{result.semantic_rank} -> +{semantic_contrib:.4f}")

        if result.keyword_rank is not None:
            keyword_contrib = 1.0 / (self.k + result.keyword_rank)
            parts.append(f"  - Keyword rank #{result.keyword_rank} -> +{keyword_contrib:.4f}")

        return "\n".join(parts)
