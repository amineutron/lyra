"""
Tests unitaires pour KeywordRetriever.
"""

import pytest

# Skip si BM25 non installe
pytest.importorskip("rank_bm25")

from lyra.rag.keyword_retriever import KeywordRetriever, KeywordResult


class TestKeywordRetriever:
    """Tests pour KeywordRetriever."""

    @pytest.fixture
    def retriever(self):
        """Cree un retriever vide."""
        return KeywordRetriever()

    def test_initialization(self):
        """Test d'initialisation."""
        retriever = KeywordRetriever()
        assert retriever.get_document_count() == 0

    def test_add_documents(self, retriever):
        """Test d'ajout de documents."""
        docs = [
            "Demarre une machine virtuelle KVM",
            "Arrete une VM proprement",
            "Liste les backups disponibles"
        ]
        metadatas = [
            {"name": "vm_start"},
            {"name": "vm_stop"},
            {"name": "backup_list"}
        ]
        ids = ["vm_1", "vm_2", "backup_1"]

        retriever.add_documents(docs, metadatas, ids)

        assert retriever.get_document_count() == 3

    def test_search_exact_match(self, retriever):
        """Test de recherche avec mot exact."""
        docs = [
            "vm_start demarre une machine virtuelle",
            "vm_stop arrete une machine virtuelle",
            "backup_list liste les sauvegardes"
        ]
        metadatas = [
            {"name": "vm_start"},
            {"name": "vm_stop"},
            {"name": "backup_list"}
        ]
        ids = ["vm_start", "vm_stop", "backup_list"]

        retriever.add_documents(docs, metadatas, ids)

        # Recherche exact "vm_start"
        results = retriever.search("vm_start", top_k=3)

        assert len(results) > 0
        assert results[0].id == "vm_start"

    def test_search_keyword_matching(self, retriever):
        """Test de recherche par mots-cles."""
        docs = [
            "Outil: vm_start - Demarre une VM KVM virtuelle",
            "Outil: backup_create - Cree un nouveau backup sauvegarde",
            "Outil: backup_list - Liste tous les backups disponibles avec backup"
        ]
        metadatas = [
            {"name": "vm_start"},
            {"name": "backup_create"},
            {"name": "backup_list"}
        ]
        ids = ["vm_start", "backup_create", "backup_list"]

        retriever.add_documents(docs, metadatas, ids)

        # "backup" devrait matcher backup_create et backup_list
        results = retriever.search("backup liste", top_k=3)

        assert len(results) >= 1
        # Au moins un resultat backup
        assert any(r.id.startswith("backup") for r in results)

    def test_search_returns_ordered_by_score(self, retriever):
        """Test que les resultats sont ordonnes par score BM25."""
        docs = [
            "VM start demarre la VM",
            "VM VM VM clone multiple VMs",
            "backup single"
        ]
        metadatas = [
            {"name": "start"},
            {"name": "clone"},
            {"name": "backup"}
        ]
        ids = ["start", "clone", "backup"]

        retriever.add_documents(docs, metadatas, ids)

        # "VM" apparait plus dans "clone" (3 fois) donc score plus eleve
        results = retriever.search("VM", top_k=3)

        assert results[0].id == "clone"
        assert results[0].score > results[1].score

    def test_search_empty_collection(self, retriever):
        """Test de recherche sur collection vide."""
        results = retriever.search("test query")
        assert results == []

    def test_search_no_match(self, retriever):
        """Test de recherche sans correspondance."""
        docs = ["document un", "document deux"]
        metadatas = [{"name": "a"}, {"name": "b"}]
        ids = ["a", "b"]

        retriever.add_documents(docs, metadatas, ids)

        # Mot qui n'existe pas
        results = retriever.search("inexistant xyz abc", top_k=3)
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

    def test_tokenization(self, retriever):
        """Test que la tokenization fonctionne correctement."""
        # Test interne de la methode _tokenize
        tokens = retriever._tokenize("Hello, World! Test-123")
        assert "hello" in tokens
        assert "world" in tokens
        assert "test" in tokens
        assert "123" in tokens

    def test_case_insensitive(self, retriever):
        """Test que la recherche est insensible a la casse."""
        # Ajouter plusieurs documents pour que BM25 ait assez de contexte IDF
        docs = [
            "Machine Virtuelle KVM demarre une VM locale",
            "Backup system pour sauvegarder les donnees",
            "Clone une copie de la VM existante",
            "Status affiche l'etat actuel du systeme"
        ]
        metadatas = [
            {"name": "vm"},
            {"name": "backup"},
            {"name": "clone"},
            {"name": "status"}
        ]
        ids = ["vm", "backup", "clone", "status"]

        retriever.add_documents(docs, metadatas, ids)

        # Recherche en minuscules - "machine" n'existe que dans doc 1
        results1 = retriever.search("machine", top_k=4)
        # Recherche en majuscules
        results2 = retriever.search("MACHINE", top_k=4)

        # Les deux recherches devraient avoir les memes resultats
        assert len(results1) > 0, "Search should find 'machine' in lowercase"
        assert len(results2) > 0, "Search should find 'MACHINE' in uppercase"
        assert results1[0].id == results2[0].id

    def test_metadata_preserved(self, retriever):
        """Test que les metadonnees sont preservees."""
        # BM25 a besoin de plusieurs documents pour calculer IDF
        docs = [
            "Document special avec keyword unique pour test",
            "Autre document backup different",
            "Troisieme document clone systeme",
            "Quatrieme document status info"
        ]
        metadatas = [
            {"name": "test", "category": "cat", "custom": "value"},
            {"name": "other", "category": "x", "custom": "y"},
            {"name": "clone", "category": "vm", "custom": "z"},
            {"name": "status", "category": "sys", "custom": "w"}
        ]
        ids = ["test_1", "other_1", "clone_1", "status_1"]

        retriever.add_documents(docs, metadatas, ids)

        # "unique" n'existe que dans le premier document
        results = retriever.search("unique special", top_k=1)
        assert len(results) > 0, "Should find document with 'unique special'"
        assert results[0].metadata["name"] == "test"
        assert results[0].metadata["category"] == "cat"
        assert results[0].metadata["custom"] == "value"

    def test_bm25_scoring(self, retriever):
        """Test que BM25 score correctement (TF-IDF with saturation)."""
        docs = [
            "vm vm vm vm vm",  # Repetition
            "vm start command",  # Une seule occurrence
            "backup only"  # Pas de "vm"
        ]
        metadatas = [{"name": f"doc{i}"} for i in range(3)]
        ids = ["doc0", "doc1", "doc2"]

        retriever.add_documents(docs, metadatas, ids)

        results = retriever.search("vm", top_k=3)

        # Le doc avec plus de "vm" devrait scorer plus haut
        assert results[0].id == "doc0"
        # Le doc sans "vm" ne devrait pas apparaitre
        assert all(r.id != "doc2" for r in results)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
