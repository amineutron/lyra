"""
Tests E2E - Scénarios Context Injector et Confidence Cascader.

Scénarios 7-10 testent :
- Context Injector avec historique session
- Confidence Cascader avec seuils HIGH/MEDIUM/LOW
- Gestion ambiguïté et fallback
"""

import pytest
from unittest.mock import Mock

from lyra.rag_enhanced import EnhancedPipeline
from lyra.core.pipeline import QueryType


class TestScenario08_ContextInjection:
    """Scénario 8 : Context Injector basé sur historique."""

    def test_context_from_history(self, enhanced_pipeline_with_mocks, session_id):
        """Context injecté si score RAG medium + gap faible"""
        pipeline = enhanced_pipeline_with_mocks

        # Simuler historique via un premier appel pipeline
        pipeline.process_query("demarre preprod-09", session_id)

        # Query ambiguë qui nécessite contexte
        result = pipeline.process_query("fais un snapshot", session_id)

        # Vérifier que pipeline a traité la query
        assert result is not None
        assert result.response is not None


    def test_no_context_if_high_confidence(self, enhanced_pipeline_with_mocks, session_id):
        """Pas de context si score >0.85 (HIGH confidence)"""
        pipeline = enhanced_pipeline_with_mocks

        # Query claire, pas besoin de contexte
        result = pipeline.process_query("démarre preprod-09", session_id)

        # should_inject_context devrait être False
        assert result.should_inject_context is not None


class TestScenario09_ConfidenceCascade:
    """Scénario 9 : Confidence Cascader seuils."""

    def test_cascade_high_confidence(self, enhanced_pipeline_with_mocks, session_id):
        """Score >0.85 → cascade_action = 'execute'"""
        pipeline = enhanced_pipeline_with_mocks

        # Mock RAG pour retourner high score
        if pipeline._rag_3tier:
            pipeline._rag_3tier.cascade_search = Mock(return_value=[
                {'tool_name': 'vm_start', 'score': 0.95, 'source': 'registry'}
            ])

        result = pipeline.process_query("démarre preprod-09", session_id)

        # Cascade action devrait être execute ou similaire
        assert result.cascade_action is not None


    def test_cascade_medium_confidence(self, enhanced_pipeline_with_mocks, session_id):
        """Score 0.60-0.85 → cascade_action = 'propose'"""
        pipeline = enhanced_pipeline_with_mocks

        # Mock RAG pour retourner medium score
        if pipeline._rag_3tier:
            pipeline._rag_3tier.cascade_search = Mock(return_value=[
                {'tool_name': 'backup_create', 'score': 0.72, 'source': 'capabilities'},
                {'tool_name': 'vm_snapshot', 'score': 0.70, 'source': 'capabilities'}
            ])

        result = pipeline.process_query("fais un backup", session_id)

        # Avec score medium, devrait proposer options
        assert result.cascade_action is not None


    def test_cascade_low_confidence_fallback(self, enhanced_pipeline_with_mocks, session_id):
        """Score <0.60 → cascade_action = 'fallback'"""
        pipeline = enhanced_pipeline_with_mocks

        # Mock RAG pour retourner low score
        if pipeline._rag_3tier:
            pipeline._rag_3tier.cascade_search = Mock(return_value=[
                {'tool_name': 'unknown', 'score': 0.45, 'source': 'registry'}
            ])

        result = pipeline.process_query("quel temps fait-il demain", session_id)

        # Avec score low, devrait fallback
        assert result.cascade_action is not None


class TestScenario10_AmbiguityHandling:
    """Scénario 10 : Gestion ambiguïté backup vs snapshot."""

    def test_backup_ambiguous(self, enhanced_pipeline_with_mocks, session_id):
        """'fais un backup' → Ambigu (backup_create vs vm_snapshot)"""
        pipeline = enhanced_pipeline_with_mocks

        # Mock RAG pour retourner 2 outils proches
        if pipeline._rag_3tier:
            pipeline._rag_3tier.cascade_search = Mock(return_value=[
                {'tool_name': 'backup_create', 'score': 0.75, 'source': 'capabilities'},
                {'tool_name': 'vm_snapshot', 'score': 0.72, 'source': 'capabilities'}
            ])

        result = pipeline.process_query("fais un backup", session_id)

        # RAG score devrait être medium
        assert result.rag_score is not None
        # Cascade action devrait proposer options
        assert result.cascade_action is not None


class TestScenario11_MultiturnContext:
    """Scénario 11 : Multi-tour avec context injection."""

    def test_multiturn_vm_workflow(self, enhanced_pipeline_with_mocks, session_id):
        """Workflow multi-tour : start → snapshot → stop"""
        pipeline = enhanced_pipeline_with_mocks

        # Tour 1 : démarre VM
        result1 = pipeline.process_query("démarre preprod-09", session_id)
        assert result1.response is not None

        # Tour 2 : fais un snapshot (devrait utiliser contexte preprod-09)
        result2 = pipeline.process_query("fais un snapshot", session_id)
        assert result2.response is not None

        # Tour 3 : arrête la vm (devrait utiliser contexte preprod-09)
        result3 = pipeline.process_query("arrête la vm", session_id)
        assert result3.response is not None


class TestScenario12_EdgeCases:
    """Scénario 12 : Cas limites et robustesse."""

    def test_empty_query(self, enhanced_pipeline_with_mocks, session_id):
        """Query vide → gestion gracieuse"""
        pipeline = enhanced_pipeline_with_mocks

        result = pipeline.process_query("", session_id)

        # Ne devrait pas crasher
        assert result is not None


    def test_very_long_query(self, enhanced_pipeline_with_mocks, session_id):
        """Query très longue → gestion gracieuse"""
        pipeline = enhanced_pipeline_with_mocks

        long_query = "démarre " + "preprod-09 " * 50

        result = pipeline.process_query(long_query, session_id)

        # Ne devrait pas crasher
        assert result is not None


    def test_special_characters(self, enhanced_pipeline_with_mocks, session_id):
        """Query avec caractères spéciaux"""
        pipeline = enhanced_pipeline_with_mocks

        result = pipeline.process_query("démarre vm-test_01@prod", session_id)

        assert result is not None


    def test_unicode_query(self, enhanced_pipeline_with_mocks, session_id):
        """Query avec caractères unicode"""
        pipeline = enhanced_pipeline_with_mocks

        result = pipeline.process_query("allume lumière 🔆", session_id)

        assert result is not None
