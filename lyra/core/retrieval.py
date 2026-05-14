"""
Lyra Core - Retriever RAG hybride.

Encapsule SemanticRetriever (ChromaDB), KeywordRetriever (BM25) et RRFFusion
pour fournir une interface unique de recherche de specs MCP.
"""

from __future__ import annotations

import sys
from typing import Optional

from .config import RAGConfig
from .types import (
    QueryType,
    CATEGORY_KEYWORDS,
    TOOL_TYPE_KEYWORDS,
    ACTION_VERBS,
    EXPLICIT_KNOWLEDGE_PATTERNS,
    ACTION_ENTITIES,
)
from .menus import LIST_VERBS
from ..rag.semantic_retriever import SemanticRetriever
from ..rag.keyword_retriever import KeywordRetriever
from ..rag.fusion import RRFFusion, FusedResult


class Retriever:
    """Retriever RAG hybride (semantic + keyword + RRF fusion).

    Gere l'indexation ChromaDB/BM25, la detection de categorie,
    et la recuperation des specs MCP pertinentes.

    Usage:
        retriever = Retriever(config)
        retriever.initialize()
        specs = retriever.retrieve(query)
        qtype = retriever.detect_query_type(query)
    """

    def __init__(self, config: RAGConfig):
        self.config = config
        self._semantic: Optional[SemanticRetriever] = None
        self._keyword: Optional[KeywordRetriever] = None
        self._fusion: Optional[RRFFusion] = None

    def initialize(self):
        """Instancie les composants RAG et indexe les outils MCP."""
        self._semantic = SemanticRetriever(
            persist_directory=self.config.rag.chromadb.persist_directory,
            collection_name=self.config.rag.chromadb.collection_name,
            embedding_model=self.config.rag.chromadb.embedding_model
        )
        self._semantic.initialize()

        self._keyword = KeywordRetriever()
        self._fusion = RRFFusion(k=self.config.rag.retrieval.rrf_k)

        # Alimenter BM25 depuis les documents ChromaDB deja enrichis
        self._index_mcp_tools()

        # Indexer la scene Iron Man (document local, pas MCP fedora)
        self._ensure_ironman_indexed()

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def retrieve(self, query: str) -> list[FusedResult]:
        """Recupere les specs MCP pertinentes via RAG hybride.

        Applique le pre-filtrage par categorie/type puis la fusion RRF ponderee.

        Args:
            query: Requete utilisateur

        Returns:
            Liste de FusedResult (specs MCP) triee par pertinence
        """
        target_category = self._detect_category(query)
        tool_type = self._detect_tool_type(query)

        # Recherche semantique (ChromaDB)
        semantic_results = self._semantic.search(
            query=query,
            top_k=self.config.rag.retrieval.semantic_top_k
        )

        # Recherche keyword (BM25)
        keyword_results = self._keyword.search(
            query=query,
            top_k=self.config.rag.retrieval.keyword_top_k
        )

        # Court-circuit si BM25 est tres confiant (score #1 > 1.2x score #2)
        if len(keyword_results) >= 2:
            bm25_top1_score = keyword_results[0].score
            bm25_top2_score = keyword_results[1].score
            confidence_ratio = bm25_top1_score / bm25_top2_score if bm25_top2_score > 0 else 0

            if confidence_ratio > 1.2:
                semantic_rank_map = {r.id: (i + 1) for i, r in enumerate(semantic_results)}
                fused = []
                for rank, kw_result in enumerate(
                    keyword_results[:self.config.rag.retrieval.fusion_top_k * 2], start=1
                ):
                    sem_rank = semantic_rank_map.get(kw_result.id, None)
                    fused.append(FusedResult(
                        document=kw_result.document,
                        metadata=kw_result.metadata,
                        rrf_score=kw_result.score / 100.0,
                        id=kw_result.id,
                        semantic_rank=sem_rank,
                        keyword_rank=rank
                    ))
            else:
                # Fusion RRF ponderee 70% BM25 / 30% semantic
                fused = self._fuse_weighted(
                    semantic_results=semantic_results,
                    keyword_results=keyword_results,
                    semantic_weight=0.3,
                    keyword_weight=0.7,
                    top_k=self.config.rag.retrieval.fusion_top_k * 2
                )
        else:
            # Pas assez de resultats keyword, fusion classique
            fused = self._fusion.fuse(
                semantic_results=semantic_results,
                keyword_results=keyword_results,
                top_k=self.config.rag.retrieval.fusion_top_k * 2
            )

        # Booster les outils du type detecte (backup vs vm)
        if tool_type and fused:
            type_results = []
            other_results = []
            for r in fused:
                name = r.metadata.get("name", "") or ""
                if isinstance(name, str) and tool_type in name.lower():
                    type_results.append(r)
                else:
                    other_results.append(r)
            if type_results:
                fused = type_results + other_results

        # Booster les resultats de la categorie/serveur detecte
        if target_category and fused:
            target_results = []
            other_results = []
            for r in fused:
                server = r.metadata.get("server", "").lower()
                if server == target_category:
                    target_results.append(r)
                else:
                    other_results.append(r)
            fused = target_results + other_results

        # Booster les outils de listing si requete de type "liste mes VMs"
        query_lower = query.lower()
        is_listing_query = any(verb in query_lower for verb in LIST_VERBS[:10])
        if is_listing_query and fused:
            listing_results = []
            other_results = []
            for r in fused:
                name = r.metadata.get("name", "") or ""
                if isinstance(name, str):
                    name_lower = name.lower()
                    if "get_all" in name_lower or "list_" in name_lower or "_status" in name_lower:
                        listing_results.append(r)
                        continue
                other_results.append(r)
            if listing_results:
                fused = listing_results + other_results

        return fused[:self.config.rag.retrieval.fusion_top_k]

    def detect_query_type(self, query: str) -> QueryType:
        """Detecte le type de requete (KNOWLEDGE vs ACTION).

        Logique:
        1. Si question explicite de connaissance -> KNOWLEDGE
        2. Si contient entite d'action (vm, backup, tv...) -> ACTION
        3. Si contient verbe d'action -> ACTION
        4. Par defaut -> ACTION

        Args:
            query: Requete utilisateur
        """
        query_lower = query.lower().strip()
        words = query_lower.split()

        # 1. Questions explicites de connaissance
        for pattern in EXPLICIT_KNOWLEDGE_PATTERNS:
            if pattern in query_lower:
                return QueryType.KNOWLEDGE

        # 2. Entite d'action
        for entity in ACTION_ENTITIES:
            if entity in words or f" {entity}" in query_lower or f"{entity} " in query_lower:
                return QueryType.ACTION

        # 3. Verbe d'action
        for word in words:
            for verb in ACTION_VERBS:
                if word.startswith(verb):
                    return QueryType.ACTION

        return QueryType.ACTION

    # ------------------------------------------------------------------
    # Helpers prives
    # ------------------------------------------------------------------

    def _index_mcp_tools(self):
        """Charge les documents enrichis depuis ChromaDB et alimente BM25."""
        try:
            collection = self._semantic._collection
            if collection is None:
                return

            results = collection.get(include=['documents', 'metadatas'])
            if not results or not results['documents']:
                return

            documents = results['documents']
            metadatas = results['metadatas']
            ids = results['ids']

            if documents:
                self._keyword.add_documents(documents, metadatas, ids)

        except Exception as e:
            print(f"[!] Indexation MCP: {e}", file=sys.stderr)

    def _ensure_ironman_indexed(self):
        """Indexe la scene Iron Man dans ChromaDB/BM25 si absente."""
        try:
            collection = self._semantic._collection
            if collection is None:
                return

            # Upsert: evite les doublons si deja indexe
            doc = (
                "Outil: ironman.run_scene\n"
                "Categorie: scene\n"
                "Description: Lance la scene Iron Man — experience cinema complete avec lumieres Hue "
                "audio-reactives via hue_beat (mode pulse palette ironman bass-only, Entertainment API "
                "DTLS 5ms), YouTube Back in Black AC/DC, Ambilight, Denon ARC. "
                "je suis iron man je suis ironman je suis tony stark tony stark iron man mode iron man "
                "scene iron man lance iron man demarre iron man active iron man hue_beat pulse ironman\n"
                "Exemples:\n"
                "  - je suis iron man\n"
                "  - je suis ironman\n"
                "  - je suis tony stark\n"
                "  - mode iron man\n"
                "  - scene iron man\n"
                "  - lance la scene iron man\n"
                "  - je suis tony\n"
                "  - demarre iron man\n"
                "  - active iron man\n"
            )
            metadata = {
                "name": "ironman.run_scene",
                "category": "scene",
                "required_params": "",
                "optional_params": "",
                "source_file": "local",
            }
            doc_id = "ironman_run_scene"

            collection.upsert(
                documents=[doc],
                metadatas=[metadata],
                ids=[doc_id],
                embeddings=self._semantic._get_embeddings([doc]),
            )

            # Sync BM25
            if self._keyword is not None:
                self._keyword.add_documents([doc], [metadata], [doc_id])

        except Exception as e:
            print(f"[!] Iron Man indexation: {e}", file=sys.stderr)

    def _sync_keyword_retriever(self):
        """Synchronise le keyword retriever avec les docs de ChromaDB."""
        try:
            collection = self._semantic._collection
            if collection is None:
                return

            result = collection.get(include=["documents", "metadatas"])
            if not result or not result.get("documents"):
                return

            documents = result["documents"]
            metadatas = result.get("metadatas", [{}] * len(documents))
            ids = result.get("ids", [f"doc_{i}" for i in range(len(documents))])

            if documents:
                self._keyword.add_documents(documents, metadatas, ids)

        except Exception:
            pass

    def _fuse_weighted(
        self,
        semantic_results: list,
        keyword_results: list,
        semantic_weight: float = 0.3,
        keyword_weight: float = 0.7,
        top_k: int = 10
    ) -> list:
        """Fusionne les resultats avec ponderation RRF personnalisee.

        Args:
            semantic_results: Resultats semantic (ChromaDB)
            keyword_results:  Resultats keyword (BM25)
            semantic_weight:  Poids semantic (defaut: 0.3)
            keyword_weight:   Poids keyword  (defaut: 0.7)
            top_k:            Nombre de resultats
        """
        k = self.config.rag.retrieval.rrf_k
        scores: dict = {}

        for rank, result in enumerate(semantic_results, start=1):
            doc_id = result.id
            rrf_contrib = semantic_weight * (1.0 / (k + rank))
            if doc_id not in scores:
                scores[doc_id] = {
                    "document": result.document,
                    "metadata": result.metadata,
                    "rrf_score": 0.0,
                    "semantic_rank": None,
                    "keyword_rank": None
                }
            scores[doc_id]["rrf_score"] += rrf_contrib
            scores[doc_id]["semantic_rank"] = rank

        for rank, result in enumerate(keyword_results, start=1):
            doc_id = result.id
            rrf_contrib = keyword_weight * (1.0 / (k + rank))
            if doc_id not in scores:
                scores[doc_id] = {
                    "document": result.document,
                    "metadata": result.metadata,
                    "rrf_score": 0.0,
                    "semantic_rank": None,
                    "keyword_rank": None
                }
            scores[doc_id]["rrf_score"] += rrf_contrib
            scores[doc_id]["keyword_rank"] = rank

        sorted_ids = sorted(
            scores.keys(),
            key=lambda x: scores[x]["rrf_score"],
            reverse=True
        )[:top_k]

        return [
            FusedResult(
                document=scores[doc_id]["document"],
                metadata=scores[doc_id]["metadata"],
                rrf_score=scores[doc_id]["rrf_score"],
                id=doc_id,
                semantic_rank=scores[doc_id]["semantic_rank"],
                keyword_rank=scores[doc_id]["keyword_rank"]
            )
            for doc_id in sorted_ids
        ]

    def _detect_category(self, query: str) -> Optional[str]:
        """Detecte la categorie/serveur cible selon les mots-cles."""
        query_lower = query.lower()

        # Priorite: "caste/cast" explicite -> CATT meme si "tv/volume" present
        if any(kw in query_lower for kw in ["caste ", "caster", "diffuse ", "streamer", " cast ", " cast"]):
            return "catt"

        for server, keywords in CATEGORY_KEYWORDS.items():
            for kw in keywords:
                if kw in query_lower:
                    return server

        return None

    def _detect_tool_type(self, query: str) -> Optional[str]:
        """Detecte le type d'outil (backup vs vm) selon les mots-cles."""
        query_lower = query.lower()

        for tool_type, keywords in TOOL_TYPE_KEYWORDS.items():
            for kw in keywords:
                if kw in query_lower:
                    return tool_type

        return None
