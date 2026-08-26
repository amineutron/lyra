"""
Tests unitaires pour SemanticRetriever.
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch

# Skip si dependencies non installees
pytest.importorskip("chromadb")
pytest.importorskip("sentence_transformers")

import chromadb

from lyra.rag.semantic_retriever import SemanticRetriever, SemanticResult


class TestSemanticRetriever:
    """Tests pour SemanticRetriever."""

    @pytest.fixture
    def temp_db(self):
        """Cree un repertoire temporaire pour ChromaDB."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def retriever(self, temp_db):
        """Cree un retriever avec DB temporaire."""
        r = SemanticRetriever(
            persist_directory=temp_db,
            collection_name="test_collection"
        )
        r.initialize()
        return r

    def test_initialization(self, temp_db):
        """Test d'initialisation."""
        retriever = SemanticRetriever(
            persist_directory=temp_db,
            collection_name="test"
        )
        retriever.initialize()

        assert retriever._client is not None
        assert retriever._collection is not None
        assert retriever._embedding_model is not None

    def test_add_documents(self, retriever):
        """Test d'ajout de documents."""
        docs = [
            "Demarre une machine virtuelle KVM",
            "Arrete une VM proprement",
            "Liste les backups disponibles"
        ]
        metadatas = [
            {"name": "vm_start", "category": "vm"},
            {"name": "vm_stop", "category": "vm"},
            {"name": "backup_list", "category": "backup"}
        ]
        ids = ["vm_1", "vm_2", "backup_1"]

        retriever.add_documents(docs, metadatas, ids)

        assert retriever.get_document_count() == 3

    def test_search_basic(self, retriever):
        """Test de recherche basique."""
        # Ajouter des documents
        docs = [
            "Demarre une machine virtuelle KVM",
            "Arrete une VM proprement ou force l'arret",
            "Liste les backups disponibles"
        ]
        metadatas = [
            {"name": "vm_start", "category": "vm"},
            {"name": "vm_stop", "category": "vm"},
            {"name": "backup_list", "category": "backup"}
        ]
        ids = ["vm_start", "vm_stop", "backup_list"]

        retriever.add_documents(docs, metadatas, ids)

        # Recherche
        results = retriever.search("lance ma VM", top_k=2)

        assert len(results) == 2
        assert isinstance(results[0], SemanticResult)
        assert results[0].id in ["vm_start", "vm_stop"]  # VM related
        assert results[0].score > 0

    def test_search_returns_ordered_by_relevance(self, retriever):
        """Test que les resultats sont ordonnes par pertinence."""
        docs = [
            "Outil: vm_start - Demarre une machine virtuelle KVM et attend SSH",
            "Outil: backup_list - Liste tous les backups Timeshift et Borg",
            "Outil: vm_clone - Clone une VM existante"
        ]
        metadatas = [
            {"name": "vm_start"},
            {"name": "backup_list"},
            {"name": "vm_clone"}
        ]
        ids = ["vm_start", "backup_list", "vm_clone"]

        retriever.add_documents(docs, metadatas, ids)

        # La query "sauvegarde" devrait matcher backup_list en premier
        results = retriever.search("liste les sauvegardes", top_k=3)

        assert results[0].id == "backup_list"

    def test_search_empty_collection(self, retriever):
        """Test de recherche sur collection vide."""
        results = retriever.search("test query")
        assert results == []

    def test_clear(self, retriever):
        """Test de clear."""
        docs = ["Document test"]
        metadatas = [{"name": "test"}]
        ids = ["test_1"]

        retriever.add_documents(docs, metadatas, ids)
        assert retriever.get_document_count() == 1

        retriever.clear()
        assert retriever.get_document_count() == 0

    def test_semantic_similarity(self, retriever):
        """Test que la recherche semantique trouve des synonymes."""
        docs = [
            "Demarre et lance une machine virtuelle KVM",
            "Supprime et detruit une VM completement",
            "Cree une sauvegarde du systeme"
        ]
        metadatas = [
            {"name": "vm_start"},
            {"name": "vm_destroy"},
            {"name": "backup_create"}
        ]
        ids = ["vm_start", "vm_destroy", "backup_create"]

        retriever.add_documents(docs, metadatas, ids)

        # "efface la VM" devrait matcher vm_destroy (synonyme de supprime/detruit)
        results = retriever.search("efface la VM", top_k=1)
        assert results[0].id == "vm_destroy"

    def test_metadata_preserved(self, retriever):
        """Test que les metadonnees sont preservees."""
        docs = ["Test document"]
        metadatas = [{"name": "test", "category": "cat", "custom": "value"}]
        ids = ["test_1"]

        retriever.add_documents(docs, metadatas, ids)

        results = retriever.search("test", top_k=1)
        assert results[0].metadata["name"] == "test"
        assert results[0].metadata["category"] == "cat"
        assert results[0].metadata["custom"] == "value"

    def test_initialize_retries_on_concurrent_table_creation(self, temp_db):
        """Regression : deux process (ex: lyra-daemon + reindex_mcp_rag_*.py)
        qui appellent PersistentClient() en meme temps sur un repertoire
        chromadb tout neuf peuvent tous les deux tenter de creer le schema
        sqlite -- l'un recoit 'table collections already exists' alors que
        la base est en realite prete. initialize() doit retenter une fois
        au lieu de laisser planter l'appelant."""
        retriever = SemanticRetriever(
            persist_directory=temp_db,
            collection_name="test_retry"
        )

        real_client = chromadb.PersistentClient(
            path=temp_db, settings=chromadb.config.Settings(anonymized_telemetry=False)
        )

        # Force le chargement paresseux avant de patcher, sinon le module
        # semantic_retriever n'a pas encore d'attribut chromadb a patcher.
        retriever._check_dependencies()

        with patch(
            "lyra.rag.semantic_retriever.chromadb.PersistentClient",
            side_effect=[
                chromadb.errors.InternalError(
                    "error returned from database: (code: 1) "
                    "table collections already exists"
                ),
                real_client,
            ],
        ) as mock_client:
            retriever.initialize()

        assert mock_client.call_count == 2
        assert retriever._client is real_client
        assert retriever._collection is not None

    def test_initialize_reraises_other_internal_errors(self, temp_db):
        """Une InternalError sans rapport avec la course de creation ne doit
        pas etre avalee par le retry."""
        retriever = SemanticRetriever(
            persist_directory=temp_db,
            collection_name="test_other_error"
        )
        retriever._check_dependencies()

        with patch(
            "lyra.rag.semantic_retriever.chromadb.PersistentClient",
            side_effect=chromadb.errors.InternalError("disk I/O error"),
        ):
            with pytest.raises(chromadb.errors.InternalError, match="disk I/O error"):
                retriever.initialize()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
