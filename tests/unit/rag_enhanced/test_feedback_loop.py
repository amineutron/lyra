"""
Tests unitaires pour FeedbackLoop.

SESSION 6 (P5) - RAG Enhanced
"""

import pytest
import time
from pathlib import Path


class TestFeedbackLoop:
    """Tests pour la boucle de feedback."""

    def test_record_success(self, tmp_path):
        """RAG score 0.90 → success"""
        from lyra.rag_enhanced.feedback_loop import FeedbackLoop

        feedback_file = tmp_path / "feedback.json"
        feedback = FeedbackLoop(feedback_file=str(feedback_file))

        feedback.record_interaction(
            query="démarre preprod-09",
            tool_name="vm_start",
            rag_score=0.90,
            success=True
        )

        stats = feedback.get_stats("vm_start")
        assert stats['success_count'] == 1
        assert stats['failure_count'] == 0

    def test_record_failure(self, tmp_path):
        """RAG score 0.40 → failure"""
        from lyra.rag_enhanced.feedback_loop import FeedbackLoop

        feedback_file = tmp_path / "feedback.json"
        feedback = FeedbackLoop(feedback_file=str(feedback_file))

        feedback.record_interaction(
            query="start vm",
            tool_name="vm_start",
            rag_score=0.40,
            success=False
        )

        stats = feedback.get_stats("vm_start")
        assert stats['success_count'] == 0
        assert stats['failure_count'] == 1

    def test_update_query_stats(self, tmp_path):
        """Moyenne score par query type"""
        from lyra.rag_enhanced.feedback_loop import FeedbackLoop

        feedback_file = tmp_path / "feedback.json"
        feedback = FeedbackLoop(feedback_file=str(feedback_file))

        feedback.record_interaction("vm query 1", "vm_start", 0.85, True)
        feedback.record_interaction("vm query 2", "vm_start", 0.75, True)

        avg_score = feedback.get_average_score("vm_start")
        assert 0.79 < avg_score < 0.81  # (0.85 + 0.75) / 2 = 0.80

    def test_suggest_enrich_slang_dict(self, tmp_path):
        """Suggère enrichissement dict slang après 3 échecs"""
        from lyra.rag_enhanced.feedback_loop import FeedbackLoop

        feedback_file = tmp_path / "feedback.json"
        feedback = FeedbackLoop(feedback_file=str(feedback_file))

        # Enregistrer 3 échecs pour query avec slang non reconnu
        for i in range(3):
            feedback.record_interaction("start vm", "vm_start", 0.40, False)

        # Devrait suggérer ajout "start" → "démarre" dans slang_dict
        suggestions = feedback.get_suggestions()
        assert len(suggestions) > 0
        assert any("slang" in s['type'].lower() for s in suggestions)

    def test_auto_enrich_after_5_failures(self, tmp_path):
        """Auto-enrichit dictionnaires après 5 échecs (seuil TOPO)"""
        from lyra.rag_enhanced.feedback_loop import FeedbackLoop

        feedback_file = tmp_path / "feedback.json"
        feedback = FeedbackLoop(feedback_file=str(feedback_file))

        # Enregistrer 5 échecs pour même pattern
        for i in range(5):
            feedback.record_interaction("boot vm", "vm_start", 0.35, False)

        # Devrait suggérer auto-enrichissement "boot"
        assert feedback.should_auto_enrich("boot")

    def test_get_success_rate(self, tmp_path):
        """Calcul taux de succès"""
        from lyra.rag_enhanced.feedback_loop import FeedbackLoop

        feedback_file = tmp_path / "feedback.json"
        feedback = FeedbackLoop(feedback_file=str(feedback_file))

        # 8 succès sur 10
        for i in range(10):
            feedback.record_interaction(
                f"query {i}",
                "vm_start",
                0.85,
                success=(i < 8)
            )

        success_rate = feedback.get_success_rate("vm_start")
        assert success_rate == 0.80  # 8/10

    def test_get_failure_patterns(self, tmp_path):
        """Identifie patterns d'échec récurrents"""
        from lyra.rag_enhanced.feedback_loop import FeedbackLoop

        feedback_file = tmp_path / "feedback.json"
        feedback = FeedbackLoop(feedback_file=str(feedback_file))

        # 3 échecs avec "start"
        feedback.record_interaction("start vm", "vm_start", 0.40, False)
        feedback.record_interaction("start preprod", "vm_start", 0.42, False)
        feedback.record_interaction("start sandbox", "vm_start", 0.38, False)

        patterns = feedback.get_failure_patterns(min_count=3)
        assert len(patterns) > 0
        assert any("start" in p['pattern'] for p in patterns)


class TestFeedbackLoopPersistence:
    """Tests pour la persistance du feedback."""

    def test_feedback_persistence(self, tmp_path):
        """Sauvegarde en fichier JSON"""
        from lyra.rag_enhanced.feedback_loop import FeedbackLoop

        feedback_file = tmp_path / "feedback.json"
        feedback = FeedbackLoop(feedback_file=str(feedback_file))

        feedback.record_interaction("query", "vm_start", 0.85, True)

        # Recharger depuis fichier
        feedback2 = FeedbackLoop(feedback_file=str(feedback_file))
        stats = feedback2.get_stats("vm_start")
        assert stats['success_count'] == 1

    def test_feedback_window_size(self, tmp_path):
        """Agrégation sur fenêtre glissante"""
        from lyra.rag_enhanced.feedback_loop import FeedbackLoop

        feedback_file = tmp_path / "feedback.json"
        feedback = FeedbackLoop(
            feedback_file=str(feedback_file),
            window_size=10
        )

        # Enregistrer 15 interactions (dépasse fenêtre)
        for i in range(15):
            feedback.record_interaction(f"query {i}", "vm_start", 0.80, True)

        # Ne devrait garder que les 10 dernières pour stats
        window = feedback.get_window("vm_start")
        assert len(window) == 10


class TestFeedbackLoopEnrichment:
    """Tests pour l'enrichissement automatique."""

    def test_extract_slang_candidates(self, tmp_path):
        """Extraction candidats slang depuis échecs"""
        from lyra.rag_enhanced.feedback_loop import FeedbackLoop

        feedback_file = tmp_path / "feedback.json"
        feedback = FeedbackLoop(feedback_file=str(feedback_file))

        # Échecs avec patterns anglais
        feedback.record_interaction("start vm", "vm_start", 0.40, False)
        feedback.record_interaction("kill vm", "vm_stop", 0.42, False)
        feedback.record_interaction("boot server", "vm_start", 0.38, False)

        candidates = feedback.extract_slang_candidates()
        assert len(candidates) > 0
        # Devrait identifier "start", "kill", "boot" comme slang
        slang_words = {c['word'] for c in candidates}
        assert "start" in slang_words or "kill" in slang_words or "boot" in slang_words

    def test_extract_synonym_candidates(self, tmp_path):
        """Extraction candidats synonymes depuis échecs"""
        from lyra.rag_enhanced.feedback_loop import FeedbackLoop

        feedback_file = tmp_path / "feedback.json"
        feedback = FeedbackLoop(feedback_file=str(feedback_file))

        # Échecs avec synonymes potentiels
        feedback.record_interaction("lance la vm", "vm_start", 0.55, False)
        feedback.record_interaction("ouvre la vm", "vm_start", 0.52, False)

        candidates = feedback.extract_synonym_candidates()
        assert len(candidates) > 0
        # Devrait identifier "lance"/"ouvre" comme synonymes de "démarre"

    def test_should_not_auto_enrich_below_threshold(self, tmp_path):
        """Pas d'auto-enrichissement sous seuil"""
        from lyra.rag_enhanced.feedback_loop import FeedbackLoop

        feedback_file = tmp_path / "feedback.json"
        feedback = FeedbackLoop(feedback_file=str(feedback_file))

        # Seulement 2 échecs (seuil = 5)
        for i in range(2):
            feedback.record_interaction("boot vm", "vm_start", 0.35, False)

        assert not feedback.should_auto_enrich("boot")


class TestFeedbackLoopGuardrails:
    """Tests pour les garde-fous."""

    def test_rotation_if_dict_full(self, tmp_path):
        """Rotation si dictionnaire plein (200 slang, 80 synonyms)"""
        from lyra.rag_enhanced.feedback_loop import FeedbackLoop

        feedback_file = tmp_path / "feedback.json"
        feedback = FeedbackLoop(feedback_file=str(feedback_file))

        # Simuler dict slang plein (200 patterns)
        feedback.slang_dict_size = 200

        # Nouvel ajout devrait déclencher rotation
        assert feedback.should_rotate_dict("slang")

    def test_promotion_after_hits(self, tmp_path):
        """Promotion après N hits sur entrée feedback"""
        from lyra.rag_enhanced.feedback_loop import FeedbackLoop

        feedback_file = tmp_path / "feedback.json"
        feedback = FeedbackLoop(
            feedback_file=str(feedback_file),
            promotion_threshold=50
        )

        # Simuler 50 hits sur entrée temporaire
        for i in range(50):
            feedback.record_hit("boot")

        # Devrait promouvoir "boot" de dict feedback vers dict permanent
        assert feedback.should_promote("boot")

    def test_rollback_on_degradation(self, tmp_path):
        """Rollback auto si taux bon MCP baisse"""
        from lyra.rag_enhanced.feedback_loop import FeedbackLoop

        feedback_file = tmp_path / "feedback.json"
        feedback = FeedbackLoop(feedback_file=str(feedback_file))

        # Enregistrer baseline bon taux (80%)
        for i in range(10):
            feedback.record_interaction(
                f"query {i}",
                "vm_start",
                0.85,
                success=(i < 8)
            )

        baseline_rate = feedback.get_success_rate("vm_start")
        assert baseline_rate == 0.80  # 8/10

        # Simuler ajout pattern qui dégrade
        feedback.mark_enrichment("boot", "slang")

        # Ajouter 5 échecs avec ce pattern
        for i in range(5):
            feedback.record_interaction("boot vm", "vm_start", 0.40, success=False)

        # Taux devrait baisser à 8/15 = 0.53
        new_rate = feedback.get_success_rate("vm_start")
        assert new_rate < baseline_rate * 0.8  # Baisse >20%

        # Devrait déclencher rollback
        assert feedback.should_rollback("boot")


class TestFeedbackLoopEdgeCases:
    """Tests pour les cas limites."""

    def test_empty_feedback(self, tmp_path):
        """Feedback vide → stats par défaut"""
        from lyra.rag_enhanced.feedback_loop import FeedbackLoop

        feedback_file = tmp_path / "feedback.json"
        feedback = FeedbackLoop(feedback_file=str(feedback_file))

        stats = feedback.get_stats("unknown_tool")
        assert stats['success_count'] == 0
        assert stats['failure_count'] == 0

    def test_concurrent_writes(self, tmp_path):
        """Écritures concurrentes → pas de corruption"""
        from lyra.rag_enhanced.feedback_loop import FeedbackLoop

        feedback_file = tmp_path / "feedback.json"
        feedback1 = FeedbackLoop(feedback_file=str(feedback_file))
        feedback2 = FeedbackLoop(feedback_file=str(feedback_file))

        # Écriture concurrente
        feedback1.record_interaction("query1", "vm_start", 0.85, True)
        feedback2.record_interaction("query2", "vm_start", 0.80, True)

        # Recharger et vérifier intégrité
        feedback3 = FeedbackLoop(feedback_file=str(feedback_file))
        stats = feedback3.get_stats("vm_start")
        assert stats['success_count'] >= 1  # Au moins 1 enregistré
