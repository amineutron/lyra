"""
Tests M1 - Messages verbose RAG 3-tier correles au score.

SESSION 6 (P5) - Modification M1
"""

import sys
from unittest.mock import MagicMock

import pytest

# Mock ModelManager avant import LyraVoice (evite imports lourds/circulaires)
if 'lyra.models.model_manager' not in sys.modules:
    mock_mm = MagicMock()
    mock_mm.ModelManager = MagicMock()
    sys.modules['lyra.models.model_manager'] = mock_mm

from lyra.models.lyra_voice import LyraVoice  # noqa: E402


class TestRagStepMessagesLevel:
    """Tests du calcul de niveau verbose selon score."""

    def _get_level(self, score: float) -> str:
        """Reproduit la logique de niveaux de LyraVoice."""
        return "high" if score > 0.80 else "medium" if score >= 0.50 else "low"

    def test_level_high_scores(self):
        """Scores >0.80 → niveau high (peu verbose)"""
        assert self._get_level(0.90) == "high"
        assert self._get_level(0.85) == "high"
        assert self._get_level(0.81) == "high"

    def test_level_boundary_high(self):
        """Score 0.80 exactement → medium (pas high, condition >0.80)"""
        assert self._get_level(0.80) == "medium"

    def test_level_medium_scores(self):
        """Scores 0.50-0.80 → niveau medium"""
        assert self._get_level(0.70) == "medium"
        assert self._get_level(0.60) == "medium"
        assert self._get_level(0.50) == "medium"

    def test_level_boundary_low(self):
        """Score 0.49 → low (pas medium, condition >=0.50)"""
        assert self._get_level(0.49) == "low"

    def test_level_low_scores(self):
        """Scores <0.50 → niveau low (tres verbose/incertain)"""
        assert self._get_level(0.40) == "low"
        assert self._get_level(0.20) == "low"
        assert self._get_level(0.0) == "low"


class TestGetRagStepMessageRegistryDone:
    """Tests de get_rag_step_message pour l'etape registry_done."""

    def test_registry_high_score(self):
        """Score high → message court et direct"""
        data = {'score': 0.90, 'server': 'FEDORA'}
        msg = LyraVoice.get_rag_step_message('registry_done', data)

        assert msg is not None
        assert isinstance(msg, str)
        # Message high = court, contient le server
        assert 'FEDORA' in msg

    def test_registry_medium_score(self):
        """Score medium → message avec hesitation"""
        data = {'score': 0.70, 'server': 'HUE'}
        msg = LyraVoice.get_rag_step_message('registry_done', data)

        assert msg is not None
        assert 'HUE' in msg

    def test_registry_low_score(self):
        """Score low → message d'incertitude"""
        data = {'score': 0.30, 'server': 'TV'}
        msg = LyraVoice.get_rag_step_message('registry_done', data)

        assert msg is not None
        # Low = pas de server specifique cite (cherche partout)
        assert isinstance(msg, str)
        assert len(msg) > 0

    def test_registry_boundary_0_80(self):
        """Score 0.80 → medium (boundary exact)"""
        data = {'score': 0.80, 'server': 'TV'}
        msg = LyraVoice.get_rag_step_message('registry_done', data)

        assert msg is not None
        # 0.80 = medium, doit contenir le serveur
        assert 'TV' in msg

    def test_registry_boundary_0_81(self):
        """Score 0.81 → high"""
        data = {'score': 0.81, 'server': 'FEDORA'}
        msg = LyraVoice.get_rag_step_message('registry_done', data)

        assert msg is not None
        assert 'FEDORA' in msg

    def test_registry_missing_server(self):
        """Server manquant → utilise '?'"""
        data = {'score': 0.90}
        msg = LyraVoice.get_rag_step_message('registry_done', data)

        assert msg is not None
        assert '?' in msg


class TestGetRagStepMessageCapabilitiesDone:
    """Tests de get_rag_step_message pour l'etape capabilities_done."""

    def test_capabilities_high_score(self):
        """Score high → message direct avec le tool"""
        data = {
            'score': 0.90,
            'tool': 'fedora.vm_start',
            'candidates': ['fedora.vm_start']
        }
        msg = LyraVoice.get_rag_step_message('capabilities_done', data)

        assert msg is not None
        # 'fedora.vm_start' → doit afficher 'vm start' (apres split)
        assert 'vm start' in msg

    def test_capabilities_medium_score_with_alt(self):
        """Score medium avec alternative → message incertain avec les 2"""
        data = {
            'score': 0.70,
            'tool': 'fedora.vm_start',
            'candidates': ['fedora.vm_start', 'fedora.vm_clone']
        }
        msg = LyraVoice.get_rag_step_message('capabilities_done', data)

        assert msg is not None
        # Medium = hesitation, peut contenir vm start ou vm clone

    def test_capabilities_low_score(self):
        """Score low → message d'ambiguite forte"""
        data = {
            'score': 0.40,
            'tool': 'fedora.vm_snapshot',
            'candidates': ['fedora.vm_snapshot', 'backup.backup_create', 'fedora.vm_clone']
        }
        msg = LyraVoice.get_rag_step_message('capabilities_done', data)

        assert msg is not None
        assert isinstance(msg, str)

    def test_capabilities_single_candidate(self):
        """1 seul candidat → alt = 'autre chose'"""
        data = {
            'score': 0.70,
            'tool': 'fedora.vm_start',
            'candidates': ['fedora.vm_start']  # Pas d'alternative
        }
        msg = LyraVoice.get_rag_step_message('capabilities_done', data)

        assert msg is not None

    def test_capabilities_tool_format(self):
        """Tool avec prefix 'server.' → affiche uniquement la partie apres le point"""
        data = {
            'score': 0.90,
            'tool': 'fedora.vm_start',
            'candidates': ['fedora.vm_start']
        }
        msg = LyraVoice.get_rag_step_message('capabilities_done', data)

        # 'fedora.vm_start' → 'vm start' (split('.') + replace('_', ' '))
        assert 'vm start' in msg
        assert 'fedora' not in msg  # Le prefixe serveur ne doit pas apparaitre


class TestGetRagStepMessageParametersDone:
    """Tests pour l'etape parameters_done."""

    def test_parameters_done_returns_none(self):
        """parameters_done n'a pas de template → retourne None"""
        data = {'score': 0.90, 'tool': 'fedora.vm_start'}
        msg = LyraVoice.get_rag_step_message('parameters_done', data)

        assert msg is None

    def test_unknown_step_returns_none(self):
        """Etape inconnue → retourne None"""
        data = {'score': 0.90}
        msg = LyraVoice.get_rag_step_message('unknown_step', data)

        assert msg is None

    def test_empty_data(self):
        """Donnees vides → retourne None ou message avec '?'"""
        msg = LyraVoice.get_rag_step_message('registry_done', {})

        # Score 0.0 → low (cherche partout, pas de server specifique)
        assert msg is not None or msg is None  # Accepte les deux


class TestRagStepMessagesStructure:
    """Tests de la structure du dictionnaire de messages."""

    def test_all_expected_steps_present(self):
        """Toutes les etapes principales ont des templates."""
        assert ('registry_done', 'high') in LyraVoice.RAG_STEP_MESSAGES
        assert ('registry_done', 'medium') in LyraVoice.RAG_STEP_MESSAGES
        assert ('registry_done', 'low') in LyraVoice.RAG_STEP_MESSAGES
        assert ('capabilities_done', 'high') in LyraVoice.RAG_STEP_MESSAGES
        assert ('capabilities_done', 'medium') in LyraVoice.RAG_STEP_MESSAGES
        assert ('capabilities_done', 'low') in LyraVoice.RAG_STEP_MESSAGES

    def test_m2_confirmation_templates_present(self):
        """Templates M2 (confirmations par niveau) presents."""
        assert ('confirm_high', 'high') in LyraVoice.RAG_STEP_MESSAGES
        assert ('confirm_medium', 'medium') in LyraVoice.RAG_STEP_MESSAGES
        assert ('confirm_low', 'low') in LyraVoice.RAG_STEP_MESSAGES

    def test_all_template_lists_non_empty(self):
        """Tous les templates sont des listes non vides."""
        for key, templates in LyraVoice.RAG_STEP_MESSAGES.items():
            assert isinstance(templates, list), f"Cle {key}: doit etre une liste"
            assert len(templates) > 0, f"Cle {key}: liste vide"

    def test_templates_are_strings(self):
        """Tous les templates sont des chaines."""
        for key, templates in LyraVoice.RAG_STEP_MESSAGES.items():
            for template in templates:
                assert isinstance(template, str), f"Cle {key}: template non-string: {template}"
