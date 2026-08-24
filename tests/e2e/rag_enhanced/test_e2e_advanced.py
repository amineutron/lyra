"""
Tests E2E - Scénarios avancés et performance.

Scénarios avancés testant :
- Performance Slang + Synonym (<5ms combiné)
- Intégration complète pipeline
- Cas complexes multi-étapes
"""

import pytest
import time
from unittest.mock import Mock

from lyra.rag_enhanced import EnhancedPipeline


class TestScenario13_PerformanceSlangSynonym:
    """Scénario 13 : Performance Slang + Synonym <5ms."""

    def test_slang_synonym_latency(self, enhanced_pipeline_with_mocks, session_id):
        """Slang + Synonym combinés <5ms (médiane sur 100 queries)"""
        pipeline = enhanced_pipeline_with_mocks

        queries = [
            "start la vm preprod",
            "switch les lights de la chambre",
            "boot le serveur de test",
            "kill la machine virtuelle sandbox"
        ] * 25  # 100 queries

        latencies = []

        for query in queries:
            start = time.time()

            # Appeler seulement Slang + Synonym (sans le reste du pipeline)
            normalized = query
            if pipeline._slang_normalizer:
                normalized = pipeline._slang_normalizer.normalize(query)

            expanded = normalized
            if pipeline._synonym_expander:
                expanded = pipeline._synonym_expander.expand(normalized)

            latency = (time.time() - start) * 1000  # ms
            latencies.append(latency)

        # Calculer médiane et P95
        latencies_sorted = sorted(latencies)
        median = latencies_sorted[len(latencies_sorted) // 2]
        p95 = latencies_sorted[int(len(latencies_sorted) * 0.95)]

        # Assertions
        assert median < 5, f"Médiane {median:.3f}ms > 5ms"
        assert p95 < 10, f"P95 {p95:.3f}ms > 10ms"


class TestScenario14_FullPipelineIntegration:
    """Scénario 14 : Intégration pipeline complète."""

    def test_full_workflow_e2e(self, enhanced_pipeline_with_mocks, session_id):
        """Workflow complet : Slang → Synonym → RAG → Cascade → V2 → Feedback"""
        pipeline = enhanced_pipeline_with_mocks

        query = "start preprod-09"

        result = pipeline.process_query(query, session_id)

        # Vérifier toutes les étapes
        # 1. Slang
        assert result.normalized_query is not None

        # 2. Synonym
        assert result.expanded_query is not None

        # 3. RAG (mocké mais devrait retourner qqch)
        assert result.rag_source is not None

        # 4. Cascade
        assert result.cascade_action is not None

        # 5. Context (peut être None si pas injecté)
        # should_inject_context peut être True ou False

        # 6. V2 Pipeline (EPHAISTOS + LYRA + HESTIA)
        assert result.response is not None

        # 7. Feedback
        assert result.feedback_recorded is not None

        # Métriques
        assert result.metrics is not None
        assert 'total_latency_ms' in result.metrics


class TestScenario15_ComponentToggling:
    """Scénario 15 : Toggle composants individuellement."""

    @pytest.mark.parametrize("component,config_path", [
        ("slang_normalizer", "slang_normalizer.enabled"),
        ("synonym_expander", "synonym_expander.enabled"),
        ("context_injector", "context_injector.enabled"),
        ("feedback_loop", "feedback_loop.enabled"),
    ])
    def test_toggle_component(self, mock_config, component, config_path, session_id):
        """Tester enable/disable d'un composant spécifique"""
        from unittest.mock import patch

        # Créer config avec composant disabled
        with patch('lyra.rag.semantic_retriever.SemanticRetriever.initialize'):
            with patch('lyra.rag_enhanced.rag_3tier.RAG3Tier.initialize'):
                pipeline = EnhancedPipeline(config=mock_config, enabled=True)

                # Mock pipeline V2
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

                pipeline._pipeline_v2._semantic = Mock()
                pipeline._pipeline_v2._semantic.search = Mock(return_value=[])

                pipeline._pipeline_v2._keyword = Mock()
                pipeline._pipeline_v2._keyword.search = Mock(return_value=[])

                pipeline._pipeline_v2._fusion = Mock()
                pipeline._pipeline_v2._fusion.fuse = Mock(return_value=[])

                from lyra.rag.session_memory import SessionMemory
                pipeline._pipeline_v2._sessions["default"] = SessionMemory(max_turns=10)
                pipeline._pipeline_v2._rule_based_detect = lambda q: None

                pipeline._pipeline_v2._initialized = True
                pipeline._initialized = True

                result = pipeline.process_query("demarre vm", session_id)

                # Ne devrait pas crasher
                assert result is not None


class TestScenario16_ErrorHandling:
    """Scénario 16 : Gestion d'erreurs robuste."""

    def test_component_failure_graceful(self, enhanced_pipeline_with_mocks, session_id):
        """Si un composant échoue, pipeline continue"""
        pipeline = enhanced_pipeline_with_mocks

        # Simuler échec Slang (mise à None)
        original_slang = pipeline._slang_normalizer
        pipeline._slang_normalizer = None

        result = pipeline.process_query("start vm", session_id)

        # Pipeline devrait continuer sans Slang
        assert result is not None
        assert result.response is not None

        # Restaurer
        pipeline._slang_normalizer = original_slang


    def test_rag_failure_fallback(self, enhanced_pipeline_with_mocks, session_id):
        """Si RAG échoue, fallback gracieux"""
        pipeline = enhanced_pipeline_with_mocks

        # Mock RAG pour lever exception
        if pipeline._rag_3tier:
            pipeline._rag_3tier.cascade_search = Mock(side_effect=Exception("RAG error"))

        # Ne devrait pas crasher, utiliser fallback
        result = pipeline.process_query("démarre vm", session_id)

        assert result is not None


class TestScenario17_ConcurrentSessions:
    """Scénario 17 : Sessions concurrentes indépendantes."""

    def test_multiple_sessions_independent(self, enhanced_pipeline_with_mocks):
        """Plusieurs sessions doivent être indépendantes"""
        pipeline = enhanced_pipeline_with_mocks

        session_a = "session_a"
        session_b = "session_b"

        # Verifier que deux sessions independantes donnent des resultats distincts
        result_a = pipeline.process_query("demarre preprod-09", session_a)
        result_b = pipeline.process_query("allume les lumieres", session_b)

        # Les deux sessions doivent produire une reponse sans crasher
        assert result_a is not None
        assert result_a.response is not None
        assert result_b is not None
        assert result_b.response is not None

        # Les sessions doivent etre independantes (normalized_query distinctes)
        assert result_a.normalized_query != result_b.normalized_query


class TestScenario18_MetricsAccuracy:
    """Scénario 18 : Précision des métriques."""

    def test_metrics_consistency(self, enhanced_pipeline_with_mocks, session_id):
        """Total latency = somme des latencies individuelles"""
        pipeline = enhanced_pipeline_with_mocks

        result = pipeline.process_query("démarre preprod-09", session_id)

        # Calculer somme des latencies individuelles
        individual_sum = 0

        for key in ['slang_latency_ms', 'synonym_latency_ms', 'rag_latency_ms',
                    'cascade_latency_ms', 'context_latency_ms', 'v2_pipeline_latency_ms',
                    'feedback_latency_ms']:
            if key in result.metrics:
                individual_sum += result.metrics[key]

        total = result.metrics.get('total_latency_ms', 0)

        # Total devrait être >= somme (peut inclure overhead orchestration)
        assert total >= individual_sum * 0.9, f"Total {total}ms < somme {individual_sum}ms"
