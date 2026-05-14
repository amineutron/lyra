"""
Lyra RAG - Semantic Retriever.

Utilise ChromaDB avec embeddings pour la recherche semantique.
"""

import os
import warnings
import logging
from typing import Optional
from dataclasses import dataclass

# Supprimer TOUS les warnings HuggingFace AVANT import
os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"

# Filtrer les warnings
warnings.filterwarnings("ignore", message=".*unauthenticated.*")
warnings.filterwarnings("ignore", message=".*HF Hub.*")
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# Supprimer les logs huggingface
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)

# Note: chromadb et sentence-transformers sont optionnels
# Installation: pip install chromadb sentence-transformers

try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False

try:
    # Importer silencieusement (supprime le warning HF Hub)
    import sys
    from io import StringIO
    _stderr = sys.stderr
    sys.stderr = StringIO()
    from sentence_transformers import SentenceTransformer
    sys.stderr = _stderr
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
except Exception:
    # Restaurer stderr en cas d'erreur
    sys.stderr = _stderr
    SENTENCE_TRANSFORMERS_AVAILABLE = False


@dataclass
class SemanticResult:
    """Resultat de recherche semantique."""
    document: str
    metadata: dict
    score: float
    id: str


class SemanticRetriever:
    """Retriever semantique base sur ChromaDB.

    Utilise des embeddings pour la recherche de similarite.
    """

    def __init__(
        self,
        persist_directory: str = ".chromadb",
        collection_name: str = "lyra_mcp_specs",
        embedding_model: str = "all-MiniLM-L6-v2"
    ):
        """Initialise le retriever.

        Args:
            persist_directory: Repertoire de persistence ChromaDB
            collection_name: Nom de la collection
            embedding_model: Modele d'embeddings sentence-transformers
        """
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self.embedding_model_name = embedding_model

        self._client: Optional[chromadb.ClientAPI] = None
        self._collection = None
        self._embedding_model = None
        # Cache dict : query_text -> embedding vector
        # Evite de reencoder la meme requete plusieurs fois en mode interactif
        self._embed_cache: dict = {}

    def _check_dependencies(self):
        """Verifie que les dependances sont installees."""
        if not CHROMADB_AVAILABLE:
            raise ImportError(
                "chromadb n'est pas installe. "
                "Installez-le avec: pip install chromadb"
            )
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            raise ImportError(
                "sentence-transformers n'est pas installe. "
                "Installez-le avec: pip install sentence-transformers"
            )

    def initialize(self):
        """Initialise ChromaDB et charge le modele d'embeddings."""
        self._check_dependencies()

        # Client ChromaDB persistant
        self._client = chromadb.PersistentClient(
            path=self.persist_directory,
            settings=Settings(anonymized_telemetry=False)
        )

        # Charger ou creer la collection
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )

        # Charger le modele d'embeddings (silencieux)
        import logging
        import sys
        from contextlib import redirect_stderr
        from io import StringIO

        # Supprimer tous les logs verbeux
        logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
        logging.getLogger("transformers").setLevel(logging.ERROR)
        logging.getLogger("mlx").setLevel(logging.ERROR)

        # Charger sans barre de progression ni messages
        with redirect_stderr(StringIO()):
            self._embedding_model = SentenceTransformer(
                self.embedding_model_name,
                device="cpu"  # CPU pour embeddings (leger)
            )

    def _get_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Genere les embeddings pour une liste de textes.

        Utilise un cache dict pour eviter de reencoder les requetes repetees
        (utile en mode interactif). Les indexations (add_documents) ne beneficient
        pas du cache mais ce n'est pas le chemin critique.
        """
        if self._embedding_model is None:
            self.initialize()

        # Identifier les textes absents du cache
        missing = [t for t in texts if t not in self._embed_cache]
        if missing:
            new_vecs = self._embedding_model.encode(missing).tolist()
            for t, vec in zip(missing, new_vecs):
                self._embed_cache[t] = vec

        return [self._embed_cache[t] for t in texts]

    def add_documents(
        self,
        documents: list[str],
        metadatas: list[dict],
        ids: list[str]
    ):
        """Ajoute des documents a la collection.

        Args:
            documents: Liste des textes
            metadatas: Metadonnees associees
            ids: Identifiants uniques
        """
        if self._collection is None:
            self.initialize()

        embeddings = self._get_embeddings(documents)

        self._collection.add(
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids
        )

    def search(
        self,
        query: str,
        top_k: int = 5
    ) -> list[SemanticResult]:
        """Recherche semantique.

        Args:
            query: Requete de recherche
            top_k: Nombre de resultats

        Returns:
            Liste de SemanticResult ordonnee par pertinence
        """
        if self._collection is None:
            self.initialize()

        query_embedding = self._get_embeddings([query])[0]

        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"]
        )

        semantic_results = []
        if results and results["documents"]:
            for i, doc in enumerate(results["documents"][0]):
                # ChromaDB retourne des distances (0 = identique)
                # On convertit en score (1 = identique)
                distance = results["distances"][0][i] if results["distances"] else 0
                score = 1 - distance

                semantic_results.append(SemanticResult(
                    document=doc,
                    metadata=results["metadatas"][0][i] if results["metadatas"] else {},
                    score=score,
                    id=results["ids"][0][i] if results["ids"] else f"doc_{i}"
                ))

        return semantic_results

    def get_document_count(self) -> int:
        """Retourne le nombre de documents dans la collection."""
        if self._collection is None:
            self.initialize()
        return self._collection.count()

    def clear(self):
        """Supprime tous les documents de la collection."""
        if self._client is None:
            self.initialize()

        # Supprimer et recreer la collection
        self._client.delete_collection(self.collection_name)
        self._collection = self._client.create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )
