"""
Tests unitaires pour RRF Fusion.
"""

import pytest

from lyra.rag.fusion import RRFFusion, FusedResult
from lyra.rag.semantic_retriever import SemanticResult
from lyra.rag.keyword_retriever import KeywordResult


class TestRRFFusion:
    """Tests pour RRFFusion."""

    @pytest.fixture
    def fusion(self):
        """Cree un fusionneur avec k=60 (standard)."""
        return RRFFusion(k=60)

    def test_initialization(self):
        """Test d'initialisation."""
        fusion = RRFFusion(k=60)
        assert fusion.k == 60

    def test_fuse_empty_results(self, fusion):
        """Test de fusion avec resultats vides."""
        result = fusion.fuse([], [], top_k=3)
        assert result == []

    def test_fuse_semantic_only(self, fusion):
        """Test de fusion avec seulement resultats semantiques."""
        semantic = [
            SemanticResult("doc1", {"name": "a"}, 0.9, "id1"),
            SemanticResult("doc2", {"name": "b"}, 0.8, "id2"),
        ]
        keyword = []

        results = fusion.fuse(semantic, keyword, top_k=3)

        assert len(results) == 2
        assert results[0].id == "id1"
        assert results[0].semantic_rank == 1
        assert results[0].keyword_rank is None

    def test_fuse_keyword_only(self, fusion):
        """Test de fusion avec seulement resultats keyword."""
        semantic = []
        keyword = [
            KeywordResult("doc1", {"name": "a"}, 5.0, "id1"),
            KeywordResult("doc2", {"name": "b"}, 3.0, "id2"),
        ]

        results = fusion.fuse(semantic, keyword, top_k=3)

        assert len(results) == 2
        assert results[0].id == "id1"
        assert results[0].keyword_rank == 1
        assert results[0].semantic_rank is None

    def test_fuse_combines_rankings(self, fusion):
        """Test que RRF combine correctement les rankings."""
        # Doc "id1" est #1 en semantic et #2 en keyword
        # Doc "id2" est #2 en semantic et #1 en keyword
        semantic = [
            SemanticResult("doc1", {"name": "a"}, 0.9, "id1"),
            SemanticResult("doc2", {"name": "b"}, 0.8, "id2"),
        ]
        keyword = [
            KeywordResult("doc2", {"name": "b"}, 5.0, "id2"),
            KeywordResult("doc1", {"name": "a"}, 3.0, "id1"),
        ]

        results = fusion.fuse(semantic, keyword, top_k=2)

        # Les deux docs devraient avoir le meme score RRF
        # (1/(60+1) + 1/(60+2)) = meme pour les deux
        assert len(results) == 2
        # Verifier que les ranks sont corrects
        for r in results:
            if r.id == "id1":
                assert r.semantic_rank == 1
                assert r.keyword_rank == 2
            elif r.id == "id2":
                assert r.semantic_rank == 2
                assert r.keyword_rank == 1

    def test_fuse_boosts_documents_in_both(self, fusion):
        """Test que les documents dans les deux rankings ont un score plus eleve."""
        # id1 apparait dans les deux, id2 et id3 dans un seul
        semantic = [
            SemanticResult("doc1", {"name": "shared"}, 0.9, "id1"),
            SemanticResult("doc2", {"name": "sem_only"}, 0.8, "id2"),
        ]
        keyword = [
            KeywordResult("doc1", {"name": "shared"}, 5.0, "id1"),
            KeywordResult("doc3", {"name": "kw_only"}, 3.0, "id3"),
        ]

        results = fusion.fuse(semantic, keyword, top_k=3)

        # id1 devrait etre premier car il a un score RRF de deux contributions
        assert results[0].id == "id1"
        assert results[0].rrf_score > results[1].rrf_score

    def test_fuse_respects_top_k(self, fusion):
        """Test que top_k limite les resultats."""
        semantic = [
            SemanticResult("doc1", {}, 0.9, "id1"),
            SemanticResult("doc2", {}, 0.8, "id2"),
            SemanticResult("doc3", {}, 0.7, "id3"),
        ]
        keyword = []

        results = fusion.fuse(semantic, keyword, top_k=2)

        assert len(results) == 2

    def test_rrf_formula(self, fusion):
        """Test que la formule RRF est correcte: 1/(k+rank)."""
        semantic = [
            SemanticResult("doc1", {"name": "a"}, 0.9, "id1"),
        ]
        keyword = []

        results = fusion.fuse(semantic, keyword, top_k=1)

        # RRF score pour rank 1 avec k=60: 1/(60+1) = 1/61
        expected = 1.0 / (60 + 1)
        assert abs(results[0].rrf_score - expected) < 0.0001

    def test_explain(self, fusion):
        """Test de la methode explain."""
        result = FusedResult(
            document="test",
            metadata={"name": "test"},
            rrf_score=0.0328,
            id="test",
            semantic_rank=1,
            keyword_rank=2
        )

        explanation = fusion.explain(result)

        assert "RRF Score: 0.0328" in explanation
        assert "Semantic rank #1" in explanation
        assert "Keyword rank #2" in explanation

    def test_different_k_values(self):
        """Test avec differentes valeurs de k."""
        semantic = [
            SemanticResult("doc", {}, 0.9, "id1"),
        ]
        keyword = []

        # k=1 (plus sensible aux differences de rang)
        fusion_k1 = RRFFusion(k=1)
        results_k1 = fusion_k1.fuse(semantic, keyword, top_k=1)

        # k=100 (moins sensible)
        fusion_k100 = RRFFusion(k=100)
        results_k100 = fusion_k100.fuse(semantic, keyword, top_k=1)

        # k=1: score = 1/2 = 0.5
        # k=100: score = 1/101 ≈ 0.0099
        assert results_k1[0].rrf_score > results_k100[0].rrf_score

    def test_fused_result_dataclass(self):
        """Test du dataclass FusedResult."""
        result = FusedResult(
            document="test doc",
            metadata={"key": "value"},
            rrf_score=0.05,
            id="test_id",
            semantic_rank=1,
            keyword_rank=None
        )

        assert result.document == "test doc"
        assert result.metadata == {"key": "value"}
        assert result.rrf_score == 0.05
        assert result.id == "test_id"
        assert result.semantic_rank == 1
        assert result.keyword_rank is None

    def test_preserves_metadata(self, fusion):
        """Test que les metadonnees sont preservees apres fusion."""
        semantic = [
            SemanticResult(
                "doc1",
                {"name": "vm_start", "category": "vm", "custom": "data"},
                0.9,
                "id1"
            ),
        ]
        keyword = []

        results = fusion.fuse(semantic, keyword, top_k=1)

        assert results[0].metadata["name"] == "vm_start"
        assert results[0].metadata["category"] == "vm"
        assert results[0].metadata["custom"] == "data"


class TestRRFIntegration:
    """Tests d'integration avec les retrievers reels."""

    @pytest.fixture
    def fusion(self):
        return RRFFusion(k=60)

    def test_realistic_scenario(self, fusion):
        """Test avec un scenario realiste de recherche MCP."""
        # Simuler une recherche "demarre ma VM"
        # - Semantic trouve vm_start en #1, vm_clone en #2
        # - Keyword trouve vm_start en #1 (exact match), vm_status en #2

        semantic = [
            SemanticResult(
                "Outil: vm_start - Demarre une VM KVM",
                {"name": "vm_start", "category": "vm"},
                0.85,
                "vm_vm_start"
            ),
            SemanticResult(
                "Outil: vm_clone - Clone une VM",
                {"name": "vm_clone", "category": "vm"},
                0.65,
                "vm_vm_clone"
            ),
            SemanticResult(
                "Outil: vm_stop - Arrete une VM",
                {"name": "vm_stop", "category": "vm"},
                0.60,
                "vm_vm_stop"
            ),
        ]

        keyword = [
            KeywordResult(
                "Outil: vm_start - Demarre une VM KVM",
                {"name": "vm_start", "category": "vm"},
                4.5,
                "vm_vm_start"
            ),
            KeywordResult(
                "Outil: vm_status - Status d'une VM",
                {"name": "vm_status", "category": "vm"},
                2.0,
                "vm_vm_status"
            ),
        ]

        results = fusion.fuse(semantic, keyword, top_k=3)

        # vm_start devrait etre #1 (present dans les deux)
        assert results[0].metadata["name"] == "vm_start"
        assert results[0].semantic_rank == 1
        assert results[0].keyword_rank == 1

        # Le score RRF de vm_start devrait etre le plus eleve
        assert all(results[0].rrf_score >= r.rrf_score for r in results)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
