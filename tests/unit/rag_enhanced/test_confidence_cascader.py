"""
Tests unitaires pour ConfidenceCascader.

SESSION 6 (P5) - RAG Enhanced
"""

import pytest
from lyra.rag_enhanced.confidence_cascader import ConfidenceCascader
from lyra.rag_enhanced.types import CascadeAction


class TestConfidenceCascader:
    """Tests pour le cascadeur de confiance."""

    def test_cascade_high_confidence(self):
        """>0.85 → EXECUTE direct"""
        cascader = ConfidenceCascader()
        rag_results = [{'tool_name': 'vm_start', 'score': 0.90}]

        action = cascader.cascade(rag_score=0.90, rag_results=rag_results)

        assert action == CascadeAction.EXECUTE

    def test_cascade_medium_confidence(self):
        """0.60-0.85 → PROPOSE + contexte si écart faible"""
        cascader = ConfidenceCascader()
        rag_results = [
            {'tool_name': 'vm_start', 'score': 0.70},
            {'tool_name': 'vm_clone', 'score': 0.65}
        ]

        action = cascader.cascade(rag_score=0.70, rag_results=rag_results)

        assert action == CascadeAction.PROPOSE
        # Écart 0.05 < 0.10 → devrait suggérer ContextInjector

    def test_cascade_medium_large_gap(self):
        """0.60-0.85 avec écart >0.10 → PROPOSE sans contexte"""
        cascader = ConfidenceCascader()
        rag_results = [
            {'tool_name': 'vm_start', 'score': 0.75},
            {'tool_name': 'backup_create', 'score': 0.55}
        ]

        action = cascader.cascade(rag_score=0.75, rag_results=rag_results)

        assert action == CascadeAction.PROPOSE
        # Écart 0.20 > 0.10 → pas besoin contexte

    def test_cascade_low_confidence(self):
        """<0.60 → FALLBACK LYRA"""
        cascader = ConfidenceCascader()
        rag_results = [{'tool_name': 'unknown', 'score': 0.45}]

        action = cascader.cascade(rag_score=0.45, rag_results=rag_results)

        assert action == CascadeAction.FALLBACK

    def test_cascade_boundary_high(self):
        """Boundary 0.80 → PROPOSE (pas EXECUTE) - seuil M2"""
        cascader = ConfidenceCascader()
        rag_results = [{'tool_name': 'vm_start', 'score': 0.80}]

        action = cascader.cascade(rag_score=0.80, rag_results=rag_results)

        # 0.80 est le seuil M2, devrait être PROPOSE (pas EXECUTE)
        # Car condition est >0.80, pas >=0.80
        assert action == CascadeAction.PROPOSE

    def test_cascade_boundary_low(self):
        """Boundary 0.50 → PROPOSE (pas FALLBACK) - seuil M2"""
        cascader = ConfidenceCascader()
        rag_results = [{'tool_name': 'vm_start', 'score': 0.50}]

        action = cascader.cascade(rag_score=0.50, rag_results=rag_results)

        # 0.50 est le seuil M2, devrait être PROPOSE
        # Car condition est >=0.50
        assert action == CascadeAction.PROPOSE

    def test_cascade_suggests_context_injection(self):
        """MEDIUM + écart <0.10 → suggère injection contexte"""
        cascader = ConfidenceCascader()
        rag_results = [
            {'tool_name': 'backup_create', 'score': 0.72},
            {'tool_name': 'vm_snapshot', 'score': 0.68}
        ]

        result = cascader.cascade_detailed(rag_score=0.72, rag_results=rag_results)

        assert result['action'] == CascadeAction.PROPOSE
        assert result['should_inject_context'] is True
        assert result['gap'] < 0.10


class TestConfidenceCascaderM2ConfidenceLevel:
    """Tests M2 - confidence_level dans cascade_detailed."""

    def test_confidence_level_high(self):
        """Score >0.80 → confidence_level='high'"""
        cascader = ConfidenceCascader()
        rag_results = [{'tool_name': 'vm_start', 'score': 0.90}]

        result = cascader.cascade_detailed(rag_score=0.90, rag_results=rag_results)

        assert 'confidence_level' in result
        assert result['confidence_level'] == 'high'
        assert result['action'] == CascadeAction.EXECUTE

    def test_confidence_level_medium(self):
        """Score 0.50-0.80 → confidence_level='medium'"""
        cascader = ConfidenceCascader()
        rag_results = [{'tool_name': 'vm_start', 'score': 0.70}]

        result = cascader.cascade_detailed(rag_score=0.70, rag_results=rag_results)

        assert result['confidence_level'] == 'medium'
        assert result['action'] == CascadeAction.PROPOSE

    def test_confidence_level_low(self):
        """Score <0.50 → confidence_level='low'"""
        cascader = ConfidenceCascader()
        rag_results = [{'tool_name': 'unknown', 'score': 0.40}]

        result = cascader.cascade_detailed(rag_score=0.40, rag_results=rag_results)

        assert result['confidence_level'] == 'low'
        assert result['action'] == CascadeAction.FALLBACK

    def test_confidence_level_boundary_0_80(self):
        """Score 0.80 → confidence_level='medium' (seuil >0.80, pas >=)"""
        cascader = ConfidenceCascader()
        rag_results = [{'tool_name': 'vm_start', 'score': 0.80}]

        result = cascader.cascade_detailed(rag_score=0.80, rag_results=rag_results)

        # 0.80 est le seuil, la condition est >0.80 donc 0.80 → medium
        assert result['confidence_level'] == 'medium'

    def test_confidence_level_boundary_0_50(self):
        """Score 0.50 → confidence_level='medium' (seuil >=0.50)"""
        cascader = ConfidenceCascader()
        rag_results = [{'tool_name': 'vm_start', 'score': 0.50}]

        result = cascader.cascade_detailed(rag_score=0.50, rag_results=rag_results)

        # 0.50 est le seuil bas, condition >=0.50 donc 0.50 → medium
        assert result['confidence_level'] == 'medium'

    def test_cascade_detailed_all_fields_present(self):
        """cascade_detailed retourne tous les champs requis."""
        cascader = ConfidenceCascader()
        rag_results = [
            {'tool_name': 'vm_start', 'score': 0.75},
            {'tool_name': 'vm_clone', 'score': 0.70}
        ]

        result = cascader.cascade_detailed(rag_score=0.75, rag_results=rag_results)

        # Tous les champs doivent etre presents
        assert 'action' in result
        assert 'confidence_level' in result
        assert 'should_inject_context' in result
        assert 'gap' in result

    def test_confidence_level_consistent_with_action(self):
        """confidence_level et action sont coherents."""
        cascader = ConfidenceCascader()
        scenarios = [
            (0.90, [{'tool_name': 't', 'score': 0.90}], 'high', CascadeAction.EXECUTE),
            (0.70, [{'tool_name': 't', 'score': 0.70}], 'medium', CascadeAction.PROPOSE),
            (0.40, [{'tool_name': 't', 'score': 0.40}], 'low', CascadeAction.FALLBACK),
        ]

        for score, results, expected_level, expected_action in scenarios:
            result = cascader.cascade_detailed(rag_score=score, rag_results=results)
            assert result['confidence_level'] == expected_level, f"Score {score}: expected {expected_level}"
            assert result['action'] == expected_action, f"Score {score}: expected {expected_action}"


class TestConfidenceCascaderMetrics:
    """Tests pour les métriques du cascadeur."""

    def test_cascade_tracks_latency(self):
        """Tracking latency par cascade"""
        cascader = ConfidenceCascader()
        rag_results = [{'tool_name': 'vm_start', 'score': 0.70}]

        cascader.cascade(rag_score=0.70, rag_results=rag_results)

        metrics = cascader.get_metrics()
        assert 'latency_ms' in metrics
        assert metrics['latency_ms'] < 2  # <2ms overhead

    def test_cascade_tracks_action_counts(self):
        """Compte les actions par type"""
        cascader = ConfidenceCascader()

        # Execute
        cascader.cascade(0.90, [{'tool_name': 'vm_start', 'score': 0.90}])
        # Propose
        cascader.cascade(0.70, [{'tool_name': 'vm_start', 'score': 0.70}])
        # Fallback
        cascader.cascade(0.40, [{'tool_name': 'vm_start', 'score': 0.40}])

        metrics = cascader.get_metrics()
        assert metrics['execute_count'] == 1
        assert metrics['propose_count'] == 1
        assert metrics['fallback_count'] == 1


class TestConfidenceCascaderEdgeCases:
    """Tests pour les cas limites."""

    def test_cascade_empty_results(self):
        """Résultats RAG vides → FALLBACK"""
        cascader = ConfidenceCascader()

        action = cascader.cascade(rag_score=0.90, rag_results=[])

        assert action == CascadeAction.FALLBACK

    def test_cascade_single_result(self):
        """1 seul résultat → pas de calcul de gap"""
        cascader = ConfidenceCascader()
        rag_results = [{'tool_name': 'vm_start', 'score': 0.70}]

        result = cascader.cascade_detailed(rag_score=0.70, rag_results=rag_results)

        assert result['action'] == CascadeAction.PROPOSE
        assert result['should_inject_context'] is False  # Pas de gap si 1 seul résultat
        assert result['gap'] is None

    def test_cascade_score_mismatch(self):
        """Score RAG != score top résultat → warning"""
        cascader = ConfidenceCascader()
        rag_results = [{'tool_name': 'vm_start', 'score': 0.90}]

        # rag_score différent de top result
        result = cascader.cascade_detailed(rag_score=0.70, rag_results=rag_results)

        # Devrait utiliser rag_score fourni, pas celui des résultats
        assert result['action'] == CascadeAction.PROPOSE
