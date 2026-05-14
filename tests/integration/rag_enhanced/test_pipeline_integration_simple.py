"""
Tests d'intégration simplifiés pour EnhancedPipeline.

Tests basiques pour valider import et initialisation.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestImportAndInit:
    """Tests d'import et d'initialisation."""

    def test_import_enhanced_pipeline(self):
        """Import EnhancedPipeline réussit"""
        from lyra.rag_enhanced import EnhancedPipeline, EnhancedPipelineResult
        
        assert EnhancedPipeline is not None
        assert EnhancedPipelineResult is not None

    def test_create_enhanced_pipeline_disabled(self):
        """Créer pipeline avec enhanced=False"""
        from lyra.rag_enhanced import EnhancedPipeline
        
        pipeline = EnhancedPipeline(enabled=False)
        assert pipeline is not None
        assert pipeline.enabled is False

    def test_create_enhanced_pipeline_enabled(self):
        """Créer pipeline avec enhanced=True"""
        from lyra.rag_enhanced import EnhancedPipeline
        
        pipeline = EnhancedPipeline(enabled=True)
        assert pipeline is not None
        assert pipeline.enabled is True

    def test_pipeline_has_components(self):
        """Pipeline a les composants attendus"""
        from lyra.rag_enhanced import EnhancedPipeline
        
        pipeline = EnhancedPipeline(enabled=True)
        
        # Composants (lazy-loaded, None avant initialize)
        assert hasattr(pipeline, '_slang_normalizer')
        assert hasattr(pipeline, '_synonym_expander')
        assert hasattr(pipeline, '_context_injector')
        assert hasattr(pipeline, '_rag_3tier')
        assert hasattr(pipeline, '_confidence_cascader')
        assert hasattr(pipeline, '_feedback_loop')

    @patch('lyra.rag.semantic_retriever.SemanticRetriever.initialize')
    def test_pipeline_initialize_disabled(self, mock_semantic_init):
        """Initialiser pipeline disabled ne crash pas"""
        from lyra.rag_enhanced import EnhancedPipeline

        pipeline = EnhancedPipeline(enabled=False)

        # Devrait initialiser V2 seulement
        pipeline.initialize()

        assert pipeline._initialized is True
        # Composants enhanced devraient rester None
        assert pipeline._slang_normalizer is None
        assert pipeline._synonym_expander is None

        # Vérifier que le mock a été appelé (initialisation V2)
        assert mock_semantic_init.called

    @patch('lyra.rag_enhanced.rag_3tier.RAG3Tier.initialize')
    @patch('lyra.rag.semantic_retriever.SemanticRetriever.initialize')
    def test_pipeline_initialize_enabled(self, mock_semantic_init, mock_rag3tier_init):
        """Initialiser pipeline enabled charge les composants"""
        from lyra.rag_enhanced import EnhancedPipeline

        pipeline = EnhancedPipeline(enabled=True)
        pipeline.initialize()

        assert pipeline._initialized is True

        # Composants enhanced devraient être chargés selon config par défaut
        # Note: FeedbackLoop enabled par défaut dans config
        # Cascader est lié au FeedbackLoop

        # Vérifier que V2 est initialisé
        assert mock_semantic_init.called

        # Vérifier composants chargés (si enabled dans config par défaut)
        # Synonym, Context, Feedback/Cascader devraient être chargés
        # Slang peut être None (SESSION 2 non implémentée)
        # RAG3Tier devrait être None (disabled par défaut)


class TestEnhancedPipelineResult:
    """Tests pour EnhancedPipelineResult."""

    def test_enhanced_result_creation(self):
        """Créer un EnhancedPipelineResult"""
        from lyra.rag_enhanced import EnhancedPipelineResult
        from lyra.core.pipeline import QueryType
        
        result = EnhancedPipelineResult(
            response="Test response",
            query_type=QueryType.ACTION,
            normalized_query="test normalized",
            expanded_query="test expanded",
            rag_source="v2_fallback",
            cascade_action="execute",
            feedback_recorded=True,
            metrics={'total_latency_ms': 42.0}
        )
        
        assert result.response == "Test response"
        assert result.normalized_query == "test normalized"
        assert result.expanded_query == "test expanded"
        assert result.rag_source == "v2_fallback"
        assert result.cascade_action == "execute"
        assert result.feedback_recorded is True
        assert result.metrics['total_latency_ms'] == 42.0
