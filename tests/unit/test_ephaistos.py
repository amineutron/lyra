"""
Tests unitaires pour EPHAISTOS.
"""

import pytest
from unittest.mock import Mock, patch

from lyra.models.ephaistos import Ephaistos, EphaistosAnalysis, EPHAISTOS_SYSTEM_PROMPT
from lyra.models.model_manager import ModelManager, ModelResponse


class TestEphaistosAnalysis:
    """Tests pour EphaistosAnalysis."""

    def test_is_ready_with_tool_and_no_missing(self):
        """Test is_ready quand pret pour execution."""
        analysis = EphaistosAnalysis(
            tool="vm_start",
            arguments={"vm_name": "preprod-09"},
            missing_args=[],
            confidence=0.95,
            reasoning="OK",
            raw_response=""
        )
        assert analysis.is_ready is True
        assert analysis.needs_clarification is False
        assert analysis.no_match is False

    def test_needs_clarification_with_missing_args(self):
        """Test needs_clarification quand args manquants."""
        analysis = EphaistosAnalysis(
            tool="vm_clone",
            arguments={},
            missing_args=["source_vm", "new_vm_name"],
            confidence=0.85,
            reasoning="VMs non specifiees",
            raw_response=""
        )
        assert analysis.is_ready is False
        assert analysis.needs_clarification is True
        assert analysis.no_match is False

    def test_no_match_when_tool_is_none(self):
        """Test no_match quand aucun outil."""
        analysis = EphaistosAnalysis(
            tool=None,
            arguments={},
            missing_args=[],
            confidence=0.0,
            reasoning="Pas d'outil",
            raw_response=""
        )
        assert analysis.is_ready is False
        assert analysis.needs_clarification is False
        assert analysis.no_match is True


class TestEphaistos:
    """Tests pour Ephaistos."""

    @pytest.fixture
    def mock_manager(self):
        """Cree un ModelManager mock."""
        return Mock(spec=ModelManager)

    @pytest.fixture
    def ephaistos(self, mock_manager):
        """Cree une instance Ephaistos."""
        return Ephaistos(mock_manager)

    def test_initialization(self, ephaistos, mock_manager):
        """Test d'initialisation."""
        assert ephaistos.model_manager == mock_manager

    def test_analyze_success(self, ephaistos, mock_manager):
        """Test d'analyse reussie."""
        mock_manager.call_ephaistos.return_value = ModelResponse(
            content='{"tool": "vm_start", "arguments": {"vm_name": "preprod-09"}, "missing_args": [], "confidence": 0.95, "reasoning": "VM explicite"}',
            model="EPHAISTOS",
            success=True
        )

        result = ephaistos.analyze(
            user_query="demarre preprod-09",
            mcp_specs=["vm_start(vm_name: string)"]
        )

        assert result.tool == "vm_start"
        assert result.arguments["vm_name"] == "preprod-09"
        assert result.missing_args == []
        assert result.confidence == 0.95

    def test_analyze_with_missing_args(self, ephaistos, mock_manager):
        """Test d'analyse avec args manquants."""
        mock_manager.call_ephaistos.return_value = ModelResponse(
            content='{"tool": "vm_clone", "arguments": {}, "missing_args": ["source_vm", "new_vm_name"], "confidence": 0.85, "reasoning": "VMs non specifiees"}',
            model="EPHAISTOS",
            success=True
        )

        result = ephaistos.analyze(
            user_query="clone ma VM",
            mcp_specs=["vm_clone(source_vm: string, new_vm_name: string)"]
        )

        assert result.tool == "vm_clone"
        assert result.arguments == {}
        assert "source_vm" in result.missing_args
        assert "new_vm_name" in result.missing_args
        assert result.needs_clarification is True

    def test_analyze_no_match(self, ephaistos, mock_manager):
        """Test quand aucun outil ne correspond."""
        mock_manager.call_ephaistos.return_value = ModelResponse(
            content='{"tool": null, "arguments": {}, "missing_args": [], "confidence": 0.0, "reasoning": "Pas d\'outil MCP"}',
            model="EPHAISTOS",
            success=True
        )

        result = ephaistos.analyze(
            user_query="quelle heure est-il",
            mcp_specs=["vm_start(vm_name: string)"]
        )

        assert result.tool is None
        assert result.no_match is True

    def test_analyze_llm_error(self, ephaistos, mock_manager):
        """Test quand le LLM echoue."""
        mock_manager.call_ephaistos.return_value = ModelResponse(
            content="",
            model="EPHAISTOS",
            success=False,
            error="Timeout"
        )

        result = ephaistos.analyze(
            user_query="demarre preprod",
            mcp_specs=[]
        )

        assert result.tool is None
        assert "Erreur" in result.reasoning

    def test_parse_json_with_markdown(self, ephaistos):
        """Test du parsing JSON avec markdown."""
        content = '''```json
{"tool": "vm_start", "arguments": {"vm_name": "test"}, "missing_args": [], "confidence": 0.9, "reasoning": "OK"}
```'''
        result = ephaistos._parse_response(content)

        assert result.tool == "vm_start"
        assert result.arguments["vm_name"] == "test"

    def test_parse_json_nested(self, ephaistos):
        """Test du parsing JSON nested."""
        content = '''Voici l'analyse: {"tool": "backup_create", "arguments": {"vm_name": "prod"}, "missing_args": [], "confidence": 0.8, "reasoning": "backup demande"}'''
        result = ephaistos._parse_response(content)

        assert result.tool == "backup_create"
        assert result.arguments["vm_name"] == "prod"

    def test_parse_json_invalid(self, ephaistos):
        """Test du parsing JSON invalide."""
        content = "This is not JSON at all"
        result = ephaistos._parse_response(content)

        assert result.tool is None
        assert result.confidence == 0.0
        assert "Parse error" in result.reasoning

    def test_parse_normalizes_null_string(self, ephaistos):
        """Test que 'null' string devient None."""
        content = '{"tool": "null", "arguments": {}, "missing_args": [], "confidence": 0.0, "reasoning": "no match"}'
        result = ephaistos._parse_response(content)

        assert result.tool is None

    def test_analyze_with_known_args(self, ephaistos, mock_manager):
        """Test d'analyse avec args deja connus."""
        mock_manager.call_ephaistos.return_value = ModelResponse(
            content='{"tool": "vm_clone", "arguments": {"source_vm": "preprod", "new_vm_name": "test"}, "missing_args": [], "confidence": 0.95, "reasoning": "Complet"}',
            model="EPHAISTOS",
            success=True
        )

        result = ephaistos.analyze(
            user_query="vers test",
            mcp_specs=["vm_clone(source_vm, new_vm_name)"],
            known_args={"source_vm": "preprod"}
        )

        assert result.tool == "vm_clone"
        assert result.is_ready is True

    def test_extract_missing_args(self, ephaistos, mock_manager):
        """Test d'extraction des args manquants."""
        initial = EphaistosAnalysis(
            tool="vm_clone",
            arguments={"source_vm": "preprod"},
            missing_args=["new_vm_name"],
            confidence=0.85,
            reasoning="",
            raw_response=""
        )

        mock_manager.call_ephaistos.return_value = ModelResponse(
            content='{"tool": "vm_clone", "arguments": {"new_vm_name": "test-clone"}, "missing_args": [], "confidence": 0.95, "reasoning": "OK"}',
            model="EPHAISTOS",
            success=True
        )

        result = ephaistos.extract_missing_args(initial, "appelle-le test-clone")

        # Les args doivent etre merges
        assert "source_vm" in result.arguments
        assert "new_vm_name" in result.arguments
        assert result.arguments["source_vm"] == "preprod"
        assert result.arguments["new_vm_name"] == "test-clone"

    def test_validate_arguments_valid(self, ephaistos, mock_manager):
        """Test de validation d'arguments valides."""
        mock_manager.call_ephaistos.return_value = ModelResponse(
            content='{"valid": true, "errors": [], "warnings": []}',
            model="EPHAISTOS",
            success=True
        )

        result = ephaistos.validate_arguments(
            tool_name="vm_start",
            arguments={"vm_name": "preprod-09"},
            tool_spec="vm_start(vm_name: string)"
        )

        assert result["valid"] is True
        assert result["errors"] == []

    def test_validate_arguments_invalid(self, ephaistos, mock_manager):
        """Test de validation d'arguments invalides."""
        mock_manager.call_ephaistos.return_value = ModelResponse(
            content='{"valid": false, "errors": ["vm_name manquant"], "warnings": []}',
            model="EPHAISTOS",
            success=True
        )

        result = ephaistos.validate_arguments(
            tool_name="vm_start",
            arguments={},
            tool_spec="vm_start(vm_name: string)"
        )

        assert result["valid"] is False
        assert "vm_name manquant" in result["errors"]

    def test_analyze_mermaid_with_topic(self, ephaistos, mock_manager):
        """Test d'extraction du topic pour Mermaid."""
        mock_manager.call_ephaistos.return_value = ModelResponse(
            content='{"tool": "generate_diagram", "arguments": {"topic": "VPN"}, "missing_args": [], "confidence": 0.95, "reasoning": "extraire VPN comme topic"}',
            model="EPHAISTOS",
            success=True
        )

        result = ephaistos.analyze(
            user_query="fait un diagramme pour expliquer le VPN",
            mcp_specs=["generate_diagram(topic?: string, mermaid_code?: string, title?: string)"]
        )

        assert result.tool == "generate_diagram"
        assert result.arguments["topic"] == "VPN"
        assert result.missing_args == []
        assert result.is_ready is True

    def test_analyze_mermaid_missing_topic(self, ephaistos, mock_manager):
        """Test quand le topic est manquant."""
        mock_manager.call_ephaistos.return_value = ModelResponse(
            content='{"tool": "generate_diagram", "arguments": {}, "missing_args": ["topic"], "confidence": 0.85, "reasoning": "diagramme demandé mais aucun sujet specifie"}',
            model="EPHAISTOS",
            success=True
        )

        result = ephaistos.analyze(
            user_query="fais moi un diagramme",
            mcp_specs=["generate_diagram(topic?: string, mermaid_code?: string, title?: string)"]
        )

        assert result.tool == "generate_diagram"
        assert result.arguments == {}
        assert "topic" in result.missing_args
        assert result.needs_clarification is True

    def test_analyze_mermaid_complex_topic(self, ephaistos, mock_manager):
        """Test d'extraction d'un topic complexe."""
        mock_manager.call_ephaistos.return_value = ModelResponse(
            content='{"tool": "generate_diagram", "arguments": {"topic": "Architecture Lyra"}, "missing_args": [], "confidence": 0.90, "reasoning": "extraire architecture Lyra comme topic"}',
            model="EPHAISTOS",
            success=True
        )

        result = ephaistos.analyze(
            user_query="cree un diagramme sur l'architecture Lyra",
            mcp_specs=["generate_diagram(topic?: string, mermaid_code?: string, title?: string)"]
        )

        assert result.tool == "generate_diagram"
        assert result.arguments["topic"] == "Architecture Lyra"
        assert result.missing_args == []
        assert result.is_ready is True


class TestEphaistosSystemPrompt:
    """Tests pour le system prompt EPHAISTOS."""

    def test_prompt_contains_json_instruction(self):
        """Test que le prompt demande du JSON."""
        assert "JSON" in EPHAISTOS_SYSTEM_PROMPT
        assert "valide" in EPHAISTOS_SYSTEM_PROMPT.lower()

    def test_prompt_contains_examples(self):
        """Test que le prompt contient des exemples."""
        assert "vm_start" in EPHAISTOS_SYSTEM_PROMPT
        assert "vm_clone" in EPHAISTOS_SYSTEM_PROMPT
        assert "EXEMPLES" in EPHAISTOS_SYSTEM_PROMPT

    def test_prompt_explains_missing_args(self):
        """Test que le prompt explique missing_args."""
        assert "missing_args" in EPHAISTOS_SYSTEM_PROMPT
        assert "obligatoire" in EPHAISTOS_SYSTEM_PROMPT.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
