"""
Tests unitaires pour LyraVoice.
"""

import pytest
from unittest.mock import Mock, patch

from lyra.models.lyra_voice import LyraVoice, LyraResponse, LYRA_SYSTEM_PROMPT_TTS as LYRA_SYSTEM_PROMPT
from lyra.models.model_manager import ModelManager, ModelResponse


class TestLyraResponse:
    """Tests pour LyraResponse."""

    def test_response_basic(self):
        """Test de reponse basique."""
        resp = LyraResponse(
            text="Quelle VM?",
            mentions_ephaistos=False,
            mentions_hestia=False
        )
        assert resp.text == "Quelle VM?"
        assert resp.mentions_ephaistos is False
        assert resp.mentions_hestia is False

    def test_response_with_mentions(self):
        """Test de reponse avec mentions."""
        resp = LyraResponse(
            text="Ephaistos m'indique qu'il manque le nom.",
            mentions_ephaistos=True,
            mentions_hestia=False
        )
        assert resp.mentions_ephaistos is True


class TestLyraVoice:
    """Tests pour LyraVoice."""

    @pytest.fixture
    def mock_manager(self):
        """Cree un ModelManager mock."""
        return Mock(spec=ModelManager)

    @pytest.fixture
    def lyra(self, mock_manager):
        """Cree une instance LyraVoice."""
        return LyraVoice(mock_manager)

    def test_initialization(self, lyra, mock_manager):
        """Test d'initialisation."""
        assert lyra.model_manager == mock_manager

    def test_probability_constants(self, lyra):
        """Test des constantes de probabilite."""
        # Les constantes sont maintenant des properties dynamiques selon tts_mode
        # tts_mode=False par defaut → valeurs TEXT
        assert lyra.mention_prob_ephaistos == 0.30  # TEXT mode par defaut
        assert 0 < lyra.mention_prob_hestia_if_ephaistos <= 1.0
        assert lyra.mention_prob_hestia_error == 0.40  # TEXT mode par defaut

    def test_question_templates_exist(self, lyra):
        """Test que les templates existent."""
        assert "vm_name" in lyra.QUESTION_TEMPLATES
        assert "source_vm" in lyra.QUESTION_TEMPLATES
        assert "default" in lyra.QUESTION_TEMPLATES

    def test_action_verbs_exist(self, lyra):
        """Test que les verbes d'action existent."""
        assert lyra.ACTION_VERBS["vm_start"] == "demarrer"
        assert lyra.ACTION_VERBS["vm_stop"] == "arreter"
        assert lyra.ACTION_VERBS["backup_create"] == "sauvegarder"

    def test_ask_clarification_with_llm(self, lyra, mock_manager):
        """Test de question de clarification via LLM."""
        mock_manager.call_lyra.return_value = ModelResponse(
            content="Quelle VM tu veux demarrer?",
            model="LYRA",
            success=True
        )

        result = lyra.ask_clarification(
            missing_args=["vm_name"],
            tool_name="vm_start"
        )

        assert "VM" in result.text or "vm" in result.text.lower()
        assert isinstance(result, LyraResponse)

    def test_ask_clarification_fallback(self, lyra, mock_manager):
        """Test de fallback quand LLM echoue."""
        mock_manager.call_lyra.return_value = ModelResponse(
            content="",
            model="LYRA",
            success=False,
            error="Timeout"
        )

        result = lyra.ask_clarification(
            missing_args=["vm_name"],
            tool_name="vm_start"
        )

        # Doit utiliser le fallback
        assert result.text != ""
        assert "vm" in result.text.lower() or "VM" in result.text

    def test_ask_clarification_multiple_args(self, lyra, mock_manager):
        """Test avec plusieurs args manquants."""
        mock_manager.call_lyra.return_value = ModelResponse(
            content="Quelle VM cloner et comment l'appeler?",
            model="LYRA",
            success=True
        )

        result = lyra.ask_clarification(
            missing_args=["source_vm", "new_vm_name"],
            tool_name="vm_clone"
        )

        assert result.text != ""

    def test_format_result_success(self, lyra, mock_manager):
        """Test de formatage de resultat reussi."""
        mock_manager.call_lyra.return_value = ModelResponse(
            content="C'est fait, preprod-09 est demarree.",
            model="LYRA",
            success=True
        )

        result = lyra.format_result(
            tool_name="vm_start",
            result="VM started successfully",
            success=True
        )

        assert result.text != ""
        assert isinstance(result, LyraResponse)

    def test_format_result_failure(self, lyra, mock_manager):
        """Test de formatage de resultat echoue."""
        mock_manager.call_lyra.return_value = ModelResponse(
            content="Il y a eu un souci avec le demarrage.",
            model="LYRA",
            success=True
        )

        result = lyra.format_result(
            tool_name="vm_start",
            result="Connection refused",
            success=False
        )

        assert result.text != ""

    def test_format_result_fallback_success(self, lyra, mock_manager):
        """Test de fallback pour resultat reussi."""
        mock_manager.call_lyra.return_value = ModelResponse(
            content="",
            model="LYRA",
            success=False
        )

        result = lyra.format_result(
            tool_name="vm_start",
            result="OK",
            success=True
        )

        assert "bien" in result.text.lower() or "vm_start" in result.text

    def test_answer_knowledge(self, lyra, mock_manager):
        """Test de reponse a une question de connaissance."""
        mock_manager.call_lyra.return_value = ModelResponse(
            content="Tu as 5 VMs en cours d'execution.",
            model="LYRA",
            success=True
        )

        result = lyra.answer_knowledge(
            question="Combien de VMs j'ai?",
            context="vm_status: 5 running VMs"
        )

        assert "5" in result.text or "VM" in result.text

    def test_greet(self, lyra):
        """Test du message d'accueil."""
        greet = lyra.greet()

        assert isinstance(greet, str)
        assert len(greet) > 10
        assert "Lyra" in greet or "lyra" in greet.lower()

    def test_goodbye(self, lyra):
        """Test du message d'au revoir."""
        bye = lyra.goodbye()

        assert isinstance(bye, str)
        assert len(bye) > 0

    def test_translate_arg(self, lyra):
        """Test de traduction d'argument."""
        assert "VM" in lyra._translate_arg("vm_name")
        assert "source" in lyra._translate_arg("source_vm")
        assert "backup" in lyra._translate_arg("backup_name")

    def test_translate_args_list(self, lyra):
        """Test de traduction d'une liste d'arguments."""
        args = ["vm_name", "backup_name"]
        translated = lyra._translate_args(args)

        assert len(translated) == 2
        assert all(isinstance(t, str) for t in translated)

    def test_format_error(self, lyra, mock_manager):
        """Test de formatage d'erreur."""
        mock_manager.call_lyra.return_value = ModelResponse(
            content="Il y a eu un probleme de connexion.",
            model="LYRA",
            success=True
        )

        result = lyra.format_error(
            tool_name="vm_start",
            error="Connection refused"
        )

        assert result.text != ""
        assert isinstance(result, LyraResponse)

    def test_format_error_non_friendly(self, lyra, mock_manager):
        """Test de formatage d'erreur non convivial."""
        result = lyra.format_error(
            tool_name="vm_start",
            error="ECONNREFUSED",
            user_friendly=False
        )

        assert "ECONNREFUSED" in result.text

    def test_confirm_action(self, lyra):
        """Test de message de confirmation."""
        msg = lyra.confirm_action(
            tool_name="vm_start",
            arguments={"vm_name": "preprod-09"}
        )

        assert "preprod-09" in msg
        assert "?" in msg

    def test_confirm_action_clone(self, lyra):
        """Test de confirmation pour clone."""
        msg = lyra.confirm_action(
            tool_name="vm_clone",
            arguments={"source_vm": "prod", "new_vm_name": "test"}
        )

        assert "prod" in msg
        assert "test" in msg


class TestLyraSystemPrompt:
    """Tests pour le system prompt LYRA."""

    def test_prompt_mentions_personality(self):
        """Test que le prompt definit la personnalite."""
        assert "PERSONNALITE" in LYRA_SYSTEM_PROMPT
        assert "amicale" in LYRA_SYSTEM_PROMPT.lower()

    def test_prompt_no_emoji_rule(self):
        """Test que le prompt interdit les emojis."""
        assert "emoji" in LYRA_SYSTEM_PROMPT.lower()
        assert "ZERO" in LYRA_SYSTEM_PROMPT or "zero" in LYRA_SYSTEM_PROMPT.lower()

    def test_prompt_mentions_colleagues(self):
        """Test que le prompt mentionne les collegues."""
        assert "EPHAISTOS" in LYRA_SYSTEM_PROMPT
        assert "HESTIA" in LYRA_SYSTEM_PROMPT

    def test_prompt_has_examples(self):
        """Test que le prompt contient des exemples."""
        assert "EXEMPLES" in LYRA_SYSTEM_PROMPT
        assert "VM" in LYRA_SYSTEM_PROMPT

    def test_prompt_tts_rules(self):
        """Test que le prompt a des regles TTS."""
        assert "TTS" in LYRA_SYSTEM_PROMPT
        assert "phrase" in LYRA_SYSTEM_PROMPT.lower()


class TestLyraMentionProbabilities:
    """Tests pour les probabilites de mention."""

    @pytest.fixture
    def lyra(self):
        """Cree une instance LyraVoice avec mock."""
        mock_manager = Mock(spec=ModelManager)
        mock_manager.call_lyra.return_value = ModelResponse(
            content="Test response",
            model="LYRA",
            success=True
        )
        return LyraVoice(mock_manager)

    @patch('random.random')
    def test_ephaistos_mention_probability(self, mock_random, lyra):
        """Test que Ephaistos est mentionne ~20% du temps."""
        # Force mention
        mock_random.return_value = 0.1  # < 0.20

        result = lyra.ask_clarification(
            missing_args=["vm_name"],
            tool_name="vm_start"
        )

        assert result.mentions_ephaistos is True

    @patch('random.random')
    def test_ephaistos_no_mention(self, mock_random, lyra):
        """Test que Ephaistos n'est pas mentionne quand random > 0.20."""
        mock_random.return_value = 0.5  # > 0.20

        result = lyra.ask_clarification(
            missing_args=["vm_name"],
            tool_name="vm_start"
        )

        assert result.mentions_ephaistos is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
