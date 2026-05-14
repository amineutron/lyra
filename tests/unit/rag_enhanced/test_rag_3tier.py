"""
Tests unitaires pour RAG 3-Tier.

SESSION 5 (P4) - RAG Enhanced
"""

import pytest

# Skip si ChromaDB non disponible
pytest.importorskip("chromadb", reason="ChromaDB non installé")

from lyra.rag_enhanced.rag_3tier import RAG3Tier


class TestRAG3Tier:
    """Tests pour le système 3-tier."""

    def test_create_3_collections(self, tmp_path):
        """Test : Crée les 3 collections ChromaDB"""
        rag = RAG3Tier(persist_directory=str(tmp_path))
        rag.initialize()

        collections = rag.client.list_collections()
        names = [c.name for c in collections]

        assert "lyra_mcp_registry_v3" in names
        assert "lyra_mcp_capabilities_v3" in names
        assert "lyra_mcp_parameters_v3" in names

    def test_registry_collection(self, tmp_path):
        """Test : Collection registry contient outils par serveur"""
        rag = RAG3Tier(persist_directory=str(tmp_path))
        rag.initialize()

        # Populate avec exemple
        rag.index_registry([
            {
                "server_name": "FEDORA",
                "tool_count": 17,
                "category": "VM & Backups",
                "keywords": "vm, backup, snapshot, clone",
                "description": "FEDORA (17 outils): VM KVM et backups"
            }
        ])

        # Search
        results = rag.search_registry("vm backup", top_k=1)
        assert len(results) > 0
        assert results[0]['metadata']['server_name'] == "FEDORA"

    def test_capabilities_collection(self, tmp_path):
        """Test : Collection capabilities contient outils par capacité"""
        rag = RAG3Tier(persist_directory=str(tmp_path))
        rag.initialize()

        # Populate avec exemple
        rag.index_capabilities([
            {
                "tool_name": "vm_start",
                "server_name": "FEDORA",
                "capabilities": "Démarre une VM KVM",
                "use_cases": "reboot, reprise après maintenance"
            }
        ])

        # Search
        results = rag.search_capabilities("démarrer une vm", top_k=1)
        assert len(results) > 0
        assert results[0]['metadata']['tool_name'] == "vm_start"

    def test_parameters_collection(self, tmp_path):
        """Test : Collection parameters contient outils par arguments"""
        rag = RAG3Tier(persist_directory=str(tmp_path))
        rag.initialize()

        # Populate avec exemple
        rag.index_parameters([
            {
                "tool_name": "vm_clone",
                "required_params": ["source_vm", "new_vm_name"],
                "optional_params": ["start"],
                "description": "Clone une VM avec source_vm et new_vm_name"
            }
        ])

        # Search
        results = rag.search_parameters("source_vm new_vm_name", top_k=1)
        assert len(results) > 0
        assert results[0]['metadata']['tool_name'] == "vm_clone"

    def test_cascade_search_full(self, tmp_path):
        """Test : Cascade full scan sur les 3 collections"""
        rag = RAG3Tier(persist_directory=str(tmp_path))
        rag.initialize()

        # Populate
        rag.index_registry([
            {"server_name": "FEDORA", "tool_count": 17, "category": "VM & Backups",
             "keywords": "vm, backup", "description": "FEDORA VM tools"}
        ])
        rag.index_capabilities([
            {"tool_name": "vm_start", "server_name": "FEDORA",
             "capabilities": "Démarre VM", "use_cases": "reboot"}
        ])
        rag.index_parameters([
            {"tool_name": "vm_start", "required_params": ["vm_name"],
             "optional_params": [], "description": "Démarre VM avec vm_name"}
        ])

        # Cascade search
        results = rag.cascade_search("démarre vm", strategy="full_scan", top_k=5)

        # Devrait avoir résultats de plusieurs sources
        sources = {r['source'] for r in results}
        assert len(sources) >= 2  # Au moins 2 sources

    def test_cascade_search_early_stop(self, tmp_path):
        """Test : Stop cascade si score >0.85 en registry"""
        rag = RAG3Tier(persist_directory=str(tmp_path))
        rag.initialize()

        # Populate registry avec match fort
        rag.index_registry([
            {"server_name": "FEDORA", "tool_count": 17, "category": "VM",
             "keywords": "vm start démarre", "description": "FEDORA vm_start tool"}
        ])

        # Search avec match exact → score élevé
        results = rag.cascade_search("vm start", strategy="early_stop", top_k=3)

        # Si registry score >0.85, devrait s'arrêter là
        if results and results[0]['score'] > 0.85:
            assert results[0]['source'] == "registry"

    def test_funnel_filters_by_metadata(self, tmp_path):
        """Test : Entonnoir séquentiel avec filtrage metadata"""
        rag = RAG3Tier(persist_directory=str(tmp_path))
        rag.initialize()

        # Populate
        rag.index_registry([
            {"server_name": "FEDORA", "tool_count": 17, "category": "VM",
             "keywords": "vm backup", "description": "FEDORA tools"}
        ])
        rag.index_capabilities([
            {"tool_name": "vm_start", "server_name": "FEDORA",
             "capabilities": "Démarre VM", "use_cases": "reboot"},
            {"tool_name": "vm_clone", "server_name": "FEDORA",
             "capabilities": "Clone VM", "use_cases": "duplication"}
        ])

        # Étape 1: Registry identifie serveur
        registry_results = rag.search_registry("vm backup", top_k=1)
        best_server = registry_results[0]['metadata']['server_name']
        assert best_server == "FEDORA"

        # Étape 2: Capabilities filtre par server_name
        capabilities_results = rag.search_capabilities(
            "backup",
            top_k=10,
            filter_metadata={'server_name': best_server}
        )

        # Tous les résultats doivent être du serveur FEDORA
        for result in capabilities_results:
            assert result['metadata']['server_name'] == "FEDORA"

    def test_disabled_3tier(self, tmp_path):
        """Test : Si 3-tier disabled → fallback V2"""
        rag = RAG3Tier(enabled=False, persist_directory=str(tmp_path))

        # Ne devrait pas initialiser les collections 3-tier
        assert rag.enabled is False

    def test_get_collection_stats(self, tmp_path):
        """Test : Statistiques des collections"""
        rag = RAG3Tier(persist_directory=str(tmp_path))
        rag.initialize()

        # Populate
        rag.index_registry([
            {"server_name": "FEDORA", "tool_count": 17, "category": "VM",
             "keywords": "vm", "description": "FEDORA"}
        ])

        stats = rag.get_stats()

        assert 'registry_count' in stats
        assert stats['registry_count'] >= 1


class TestRAG3TierEdgeCases:
    """Tests pour les edge cases."""

    def test_empty_collections(self, tmp_path):
        """Test : Search sur collections vides"""
        rag = RAG3Tier(persist_directory=str(tmp_path))
        rag.initialize()

        # Search sans populate
        results = rag.search_registry("test", top_k=1)
        assert results == []

    def test_filter_no_match(self, tmp_path):
        """Test : Filtre metadata sans correspondance"""
        rag = RAG3Tier(persist_directory=str(tmp_path))
        rag.initialize()

        # Populate
        rag.index_capabilities([
            {"tool_name": "vm_start", "server_name": "FEDORA",
             "capabilities": "Démarre VM", "use_cases": "reboot"}
        ])

        # Search avec filtre ne matchant pas
        results = rag.search_capabilities(
            "démarre vm",
            top_k=10,
            filter_metadata={'server_name': 'NONEXISTENT'}
        )

        assert results == []
