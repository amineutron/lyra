"""
Lyra RAG - Keyword Retriever.

Utilise BM25 pour la recherche par mots-cles.
"""

import re
import unicodedata
from typing import Optional
from dataclasses import dataclass

# Note: rank_bm25 est optionnel
# Installation: pip install rank-bm25

try:
    from rank_bm25 import BM25Okapi
    BM25_AVAILABLE = True
except ImportError:
    BM25_AVAILABLE = False


@dataclass
class KeywordResult:
    """Resultat de recherche par mots-cles."""
    document: str
    metadata: dict
    score: float
    id: str


class KeywordRetriever:
    """Retriever par mots-cles base sur BM25.

    BM25 (Best Matching 25) est un algorithme de ranking
    base sur TF-IDF avec saturation.
    """

    def __init__(self):
        """Initialise le retriever."""
        self._documents: list[str] = []
        self._metadatas: list[dict] = []
        self._ids: list[str] = []
        self._bm25: Optional[BM25Okapi] = None
        self._tokenized_docs: list[list[str]] = []

    def _check_dependencies(self):
        """Verifie que BM25 est installe."""
        if not BM25_AVAILABLE:
            raise ImportError(
                "rank-bm25 n'est pas installe. "
                "Installez-le avec: pip install rank-bm25"
            )

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize un texte en mots.

        Args:
            text: Texte a tokenizer

        Returns:
            Liste de tokens en minuscules sans accents
        """
        # Minuscules + suppression accents (NFD decomposition) + split sur non-alphanumerique
        # Ex: "Démarre" -> "demarre", "arrête" -> "arrete"
        text = text.lower()
        text = unicodedata.normalize('NFD', text)
        text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
        tokens = re.findall(r'\w+', text)
        return tokens

    def add_documents(
        self,
        documents: list[str],
        metadatas: list[dict],
        ids: list[str]
    ):
        """Ajoute des documents a l'index.

        Args:
            documents: Liste des textes
            metadatas: Metadonnees associees
            ids: Identifiants uniques
        """
        self._check_dependencies()

        self._documents.extend(documents)
        self._metadatas.extend(metadatas)
        self._ids.extend(ids)

        # Tokenizer tous les documents
        for doc in documents:
            self._tokenized_docs.append(self._tokenize(doc))

        # Reconstruire l'index BM25
        self._bm25 = BM25Okapi(self._tokenized_docs)

    def search(
        self,
        query: str,
        top_k: int = 5
    ) -> list[KeywordResult]:
        """Recherche par mots-cles.

        Args:
            query: Requete de recherche
            top_k: Nombre de resultats

        Returns:
            Liste de KeywordResult ordonnee par score BM25
        """
        if self._bm25 is None or not self._documents:
            return []

        query_tokens = self._tokenize(query)
        scores = self._bm25.get_scores(query_tokens)

        # Trier par score decroissant
        scored_indices = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True
        )[:top_k]

        results = []
        for idx in scored_indices:
            if scores[idx] > 0:  # Ignorer les scores nuls
                results.append(KeywordResult(
                    document=self._documents[idx],
                    metadata=self._metadatas[idx],
                    score=scores[idx],
                    id=self._ids[idx]
                ))

        return results

    def get_document_count(self) -> int:
        """Retourne le nombre de documents indexes."""
        return len(self._documents)

    def clear(self):
        """Supprime tous les documents."""
        self._documents = []
        self._metadatas = []
        self._ids = []
        self._tokenized_docs = []
        self._bm25 = None
