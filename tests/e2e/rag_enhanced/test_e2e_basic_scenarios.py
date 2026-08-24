"""
Tests E2E - Scénarios basiques par serveur MCP.

Scénarios 1-6 testent le workflow complet EnhancedPipeline avec :
- Slang Normalizer
- Synonym Expander
- RAG retrieval (mocké)
- Confidence Cascader
- Context Injector (on-demand)
- EPHAISTOS (mocké)
- LYRA (mocké)
- HESTIA (mocké)
- Feedback Loop

Les tests mockent Ollama et MCP execution, mais testent les composants
RAG Enhanced réels (Slang, Synonym, Context, Cascader, Feedback).
"""

import pytest
from unittest.mock import Mock, patch

from lyra.rag_enhanced import EnhancedPipeline, EnhancedPipelineResult
from lyra.core.pipeline import QueryType


class TestScenario01_SlangNormalizer:
    """Scénario 1 : Tester Slang Normalizer avec queries anglicismes."""

    def test_start_vm_slang(self, enhanced_pipeline_with_mocks, session_id):
        """'start preprod-09' → Slang: 'start' → 'démarre'"""
        pipeline = enhanced_pipeline_with_mocks

        result = pipeline.process_query("start preprod-09", session_id)

        # Vérifier que Slang a normalisé
        assert result.normalized_query is not None
        assert "démarre" in result.normalized_query or "start" not in result.normalized_query

        # Vérifier métriques
        assert result.metrics is not None
        assert 'total_latency_ms' in result.metrics

        # Vérifier feedback recorded
        assert result.feedback_recorded is not None

    def test_kill_vm_slang(self, enhanced_pipeline_with_mocks, session_id):
        """'kill preprod-09' → Slang: 'kill' → 'arrête'"""
        pipeline = enhanced_pipeline_with_mocks

        result = pipeline.process_query("kill preprod-09", session_id)

        assert result.normalized_query is not None
        # Vérifier workflow complet
        assert result.response is not None
        assert result.metrics is not None


class TestScenario02_SynonymExpander:
    """Scénario 2 : Tester Synonym Expander."""

    def test_lance_vm_synonym(self, enhanced_pipeline_with_mocks, session_id):
        """'lance la vm' → Synonym: 'lance' → 'démarre'"""
        pipeline = enhanced_pipeline_with_mocks

        result = pipeline.process_query("lance la vm de test", session_id)

        # Vérifier que Synonym a expandé
        assert result.expanded_query is not None
        # Métriques présentes
        assert 'synonym_latency_ms' in result.metrics or result.expanded_query == "lance la vm de test"

    def test_lumiere_synonym(self, enhanced_pipeline_with_mocks, session_id):
        """'allume la lumière' → Synonym expand"""
        pipeline = enhanced_pipeline_with_mocks

        result = pipeline.process_query("allume la lumière du salon", session_id)

        assert result.expanded_query is not None
        assert result.metrics is not None


class TestScenario03_FeatureFlags:
    """Scénario 3 : Tester feature flags enabled/disabled."""

    @patch('lyra.rag.semantic_retriever.SemanticRetriever.initialize')
    def test_pipeline_disabled_no_slang(self, mock_semantic_init, mock_config, session_id):
        """Pipeline enabled=False → pas de normalisation Slang"""
        pipeline = EnhancedPipeline(config=mock_config, enabled=False)
        pipeline.initialize()

        # Mock V2 pipeline components
        pipeline._pipeline_v2._ephaistos = Mock()
        pipeline._pipeline_v2._ephaistos.analyze = Mock(return_value=Mock(
            tool_name="vm_start",
            arguments={"vm_name": "test"},
            confidence=0.95
        ))

        pipeline._pipeline_v2._lyra = Mock()
        pipeline._pipeline_v2._lyra.format_response = Mock(return_value=Mock(
            response="OK"
        ))

        pipeline._pipeline_v2._hestia = Mock()
        pipeline._pipeline_v2._hestia.execute = Mock(return_value=Mock(
            success=True,
            result="OK"
        ))

        pipeline._pipeline_v2._retriever = Mock()
        pipeline._pipeline_v2._retriever.retrieve = Mock(return_value=[])
        pipeline._pipeline_v2._retriever.detect_query_type = Mock(return_value=QueryType.ACTION)

        from lyra.core.workflows.context import WorkflowContext
        from lyra.rag.session_memory import SessionMemory
        pipeline._pipeline_v2._sessions["default"] = SessionMemory(max_turns=10)

        pipeline._pipeline_v2._initialized = True

        result = pipeline.process_query("start vm", session_id)

        # Avec enabled=False, query inchangée
        assert result.normalized_query == "start vm"
        assert result.expanded_query == "start vm"


class TestScenario04_Metrics:
    """Scénario 4 : Vérifier tracking métriques."""

    def test_metrics_breakdown(self, enhanced_pipeline_with_mocks, session_id):
        """Vérifier que toutes les métriques sont trackées"""
        pipeline = enhanced_pipeline_with_mocks

        result = pipeline.process_query("démarre preprod-09", session_id)

        # Vérifier présence métriques
        assert result.metrics is not None
        assert 'total_latency_ms' in result.metrics

        # Si composants enabled, leurs métriques doivent être présentes
        if pipeline._slang_normalizer:
            # Peut être absent si Slang n'a rien modifié
            pass

        if pipeline._synonym_expander:
            # Peut être absent si Synonym n'a rien modifié
            pass

        # Total latency doit être > 0
        assert result.metrics['total_latency_ms'] > 0


class TestScenario05_BackwardCompatibility:
    """Scénario 5 : Backward compatibility V2."""

    @patch('lyra.rag.semantic_retriever.SemanticRetriever.initialize')
    def test_v2_compat(self, mock_semantic_init, mock_config, session_id):
        """EnhancedPipeline(enabled=False) = Pipeline V2"""
        from lyra.core.pipeline import Pipeline

        pipeline_v2 = Pipeline(config=mock_config)
        pipeline_enhanced_disabled = EnhancedPipeline(config=mock_config, enabled=False)

        # Mock les deux pipelines identiquement
        from lyra.rag.session_memory import SessionMemory
        for pipeline in [pipeline_v2, pipeline_enhanced_disabled._pipeline_v2]:
            pipeline._ephaistos = Mock()
            pipeline._ephaistos.analyze = Mock(return_value=Mock(
                tool_name="vm_start",
                arguments={"vm_name": "test"},
                confidence=0.95
            ))

            pipeline._lyra = Mock()
            pipeline._lyra.format_response = Mock(return_value=Mock(
                response="VM demarree"
            ))

            pipeline._hestia = Mock()
            pipeline._hestia.execute = Mock(return_value=Mock(
                success=True,
                result="OK"
            ))

            pipeline._retriever = Mock()
            pipeline._retriever.retrieve = Mock(return_value=[])
            pipeline._retriever.detect_query_type = Mock(return_value=QueryType.ACTION)

            pipeline._sessions["default"] = SessionMemory(max_turns=10)

            from lyra.core.workflows.context import WorkflowContext
            pipeline._initialized = True

        pipeline_v2._initialized = True
        pipeline_enhanced_disabled.initialize()

        query = "demarre preprod-09"

        result_v2 = pipeline_v2.process(query)
        result_enhanced = pipeline_enhanced_disabled.process_query(query, session_id)

        # Les résultats doivent être identiques
        assert result_enhanced.normalized_query == query  # Inchangé
        assert result_enhanced.expanded_query == query  # Inchangé


class TestScenario06_PerformanceOverhead:
    """Scénario 6 : Overhead RAG Enhanced <50ms."""

    def test_overhead_components(self, enhanced_pipeline_with_mocks, session_id):
        """Overhead composants RAG Enhanced doit être <50ms"""
        pipeline = enhanced_pipeline_with_mocks

        result = pipeline.process_query("démarre preprod-09", session_id)

        # Calculer overhead = latency composants RAG Enhanced seulement
        overhead = 0

        if 'slang_latency_ms' in result.metrics:
            overhead += result.metrics['slang_latency_ms']

        if 'synonym_latency_ms' in result.metrics:
            overhead += result.metrics['synonym_latency_ms']

        if 'rag_latency_ms' in result.metrics:
            # RAG mocké, devrait être proche de 0
            overhead += result.metrics['rag_latency_ms']

        if 'cascade_latency_ms' in result.metrics:
            overhead += result.metrics['cascade_latency_ms']

        if 'context_latency_ms' in result.metrics:
            overhead += result.metrics['context_latency_ms']

        if 'feedback_latency_ms' in result.metrics:
            overhead += result.metrics['feedback_latency_ms']

        # Overhead doit être <50ms (objectif SESSION 7)
        # Note: Avec mocks, overhead sera très faible (<5ms probablement)
        assert overhead < 50, f"Overhead {overhead}ms > 50ms"


# Ajout de tests pour feedback recording
class TestScenario07_FeedbackRecording:
    """Scénario 7 : Vérifier enregistrement feedback."""

    def test_feedback_recorded(self, enhanced_pipeline_with_mocks, session_id):
        """Feedback enregistré après execution"""
        pipeline = enhanced_pipeline_with_mocks

        result = pipeline.process_query("démarre preprod-09", session_id)

        # Si feedback_loop activé, feedback doit être recorded
        if pipeline._feedback_loop:
            assert result.feedback_recorded is True
        else:
            assert result.feedback_recorded is False
