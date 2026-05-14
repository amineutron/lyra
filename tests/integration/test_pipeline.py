"""
Tests d'integration pour le Pipeline RAG.

Ces tests verifient le workflow complet:
1. Detection type query
2. RAG retrieval (mocke)
3. EPHAISTOS analyse (mocke)
4. LYRA dialogue (mocke)
5. HESTIA execution (mocke)
6. Multi-tour avec session memory
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from dataclasses import dataclass

from lyra.core.pipeline import Pipeline, PipelineResult, QueryType
from lyra.core.config import RAGConfig
from lyra.models.ephaistos import EphaistosAnalysis
from lyra.models.lyra_voice import LyraResponse
from lyra.hestia.executor import ExecutionResult


@pytest.fixture
def mock_config():
    """Configuration mockee pour les tests."""
    config = RAGConfig()
    config.llm = {"base_url": "http://localhost:11434", "timeout": 120}
    config.mcp = {"servers": {}}
    return config


@pytest.fixture
def pipeline_with_mocks(mock_config):
    """Pipeline avec tous les composants mockes."""
    pipeline = Pipeline(mock_config)

    # Mock les composants
    pipeline._retriever = Mock()
    pipeline._model_manager = Mock()
    pipeline._ephaistos = Mock()
    pipeline._lyra = Mock()
    pipeline._hestia = Mock()

    # Session memory reelle pour tester le multi-tour
    from lyra.rag.session_memory import SessionMemory
    pipeline._session = SessionMemory(max_turns=10)

    pipeline._initialized = True

    # Creer WorkflowContext avec les mocks
    from lyra.core.workflows.context import WorkflowContext
    pipeline._ctx = WorkflowContext(
        hestia=pipeline._hestia,
        lyra=pipeline._lyra,
        ephaistos=pipeline._ephaistos,
        session=pipeline._session,
        tts_mode=False,
        prepare_execution=None,
        route_query=None,
    )

    # Disable rule-based detect so EPHAISTOS mocks are used
    pipeline._rule_based_detect = lambda q: None

    # Configure HESTIA mock for VM status calls used in vm_clone workflow
    # Use DEFAULT to fall through to return_value for non-vm_status calls
    from lyra.hestia.executor import ExecutionResult
    from unittest.mock import DEFAULT as MOCK_DEFAULT
    def _mock_hestia_execute(tool_name, arguments=None, **kwargs):
        arguments = arguments or {}
        if "vm_status" in tool_name and not arguments.get("vm_name"):
            return ExecutionResult(success=True, content="preprod-09  stopped  -  -\npreprod-02  stopped  -  -\n")
        if "vm_status" in tool_name and arguments.get("vm_name") == "preprod-09":
            return ExecutionResult(success=True, content="Status: Arretee\n")
        return MOCK_DEFAULT  # Fall through to Mock's return_value
    pipeline._hestia.execute = Mock(side_effect=_mock_hestia_execute)
    pipeline._hestia.execute.return_value = ExecutionResult(success=True, content="")

    return pipeline


class TestQueryTypeDetection:
    """Tests de detection du type de requete."""

    def test_detect_knowledge_quoi(self, mock_config):
        """Detecte 'c'est quoi' comme knowledge."""
        pipeline = Pipeline(mock_config)
        assert pipeline.detect_query_type("c'est quoi vm_start") == QueryType.KNOWLEDGE

    def test_detect_knowledge_comment(self, mock_config):
        """Detecte 'comment' comme knowledge."""
        pipeline = Pipeline(mock_config)
        assert pipeline.detect_query_type("comment fonctionne le backup") == QueryType.KNOWLEDGE

    def test_detect_knowledge_quest_ce_que(self, mock_config):
        """Detecte 'qu'est-ce que' comme knowledge."""
        pipeline = Pipeline(mock_config)
        assert pipeline.detect_query_type("qu'est-ce que vm_clone") == QueryType.KNOWLEDGE

    def test_detect_action_demarre(self, mock_config):
        """Detecte 'demarre' comme action."""
        pipeline = Pipeline(mock_config)
        assert pipeline.detect_query_type("demarre preprod-09") == QueryType.ACTION

    def test_detect_action_clone(self, mock_config):
        """Detecte 'clone' comme action."""
        pipeline = Pipeline(mock_config)
        assert pipeline.detect_query_type("clone ma VM") == QueryType.ACTION

    def test_detect_action_backup(self, mock_config):
        """Detecte 'backup' comme action."""
        pipeline = Pipeline(mock_config)
        assert pipeline.detect_query_type("backup preprod-09") == QueryType.ACTION

    def test_detect_action_liste(self, mock_config):
        """Detecte 'liste' comme action."""
        pipeline = Pipeline(mock_config)
        assert pipeline.detect_query_type("liste les VMs") == QueryType.ACTION

    def test_detect_action_default(self, mock_config):
        """Par defaut, detecte comme action."""
        pipeline = Pipeline(mock_config)
        assert pipeline.detect_query_type("preprod-09 status") == QueryType.ACTION

    def test_detect_action_fais(self, mock_config):
        """Detecte 'fais' comme action."""
        pipeline = Pipeline(mock_config)
        assert pipeline.detect_query_type("fais un backup de test-vm") == QueryType.ACTION


class TestActionWorkflow:
    """Tests du workflow action complet."""

    def test_action_with_complete_args(self, pipeline_with_mocks):
        """Test action avec arguments complets."""
        pipeline = pipeline_with_mocks

        # Mock RAG results
        mock_fused = Mock()
        mock_fused.document = "vm_start(vm_name: string) - Demarre une VM"
        pipeline._retriever.retrieve.return_value = [mock_fused]

        # Mock EPHAISTOS - args complets
        pipeline._ephaistos.analyze_with_retry.return_value = EphaistosAnalysis(
            tool="vm_start",
            arguments={"vm_name": "preprod-09"},
            missing_args=[],
            confidence=0.95,
            reasoning="VM explicitement nommee",
            raw_response="{}"
        )

        # Mock LYRA confirmation
        pipeline._lyra.confirm_action.return_value = "Je vais demarrer preprod-09. Tu confirmes?"

        # Process
        result = pipeline.process("demarre preprod-09")

        assert result.query_type == QueryType.ACTION
        assert result.tool_call is not None
        assert "vm_start" in result.tool_call["name"]
        assert result.tool_call["arguments"]["vm_name"] == "preprod-09"
        assert len(result.pending_args) == 0
        assert not result.executed

    def test_action_with_missing_args(self, pipeline_with_mocks):
        """Test action avec arguments manquants."""
        pipeline = pipeline_with_mocks

        # Mock RAG results
        mock_fused = Mock()
        mock_fused.document = "vm_clone(source_vm: string, new_vm_name: string)"
        pipeline._retriever.retrieve.return_value = [mock_fused]

        # Mock EPHAISTOS - args manquants
        pipeline._ephaistos.analyze_with_retry.return_value = EphaistosAnalysis(
            tool="vm_clone",
            arguments={},
            missing_args=["source_vm", "new_vm_name"],
            confidence=0.85,
            reasoning="Intention claire mais VMs non specifiees",
            raw_response="{}"
        )

        # Mock LYRA question
        pipeline._lyra.ask_clarification.return_value = LyraResponse(
            text="D'accord pour cloner. C'est quelle VM source, et comment tu veux appeler la copie?",
            mentions_ephaistos=False,
            mentions_hestia=False
        )

        # Process
        result = pipeline.process("clone ma VM")

        assert result.query_type == QueryType.ACTION
        assert result.tool_call["name"] == "vm_clone"
        assert "source_vm" in result.pending_args
        assert "new_vm_name" in result.pending_args

        # Verifier que l'action est en attente
        pending = pipeline.get_pending_action()
        assert pending is not None
        assert pending.tool_name == "vm_clone"

    def test_action_no_tool_match(self, pipeline_with_mocks):
        """Test action sans outil correspondant."""
        pipeline = pipeline_with_mocks

        # Mock RAG results vides
        pipeline._retriever.retrieve.return_value = []

        # Process
        result = pipeline.process("fais quelque chose d'impossible")

        assert result.query_type == QueryType.ACTION
        assert result.error is not None
        assert "outil" in result.response.lower()


class TestMultiTurnConversation:
    """Tests du workflow multi-tour."""

    def test_clarification_then_complete(self, pipeline_with_mocks):
        """Test: clarification puis completion des arguments."""
        pipeline = pipeline_with_mocks

        # Setup initial - args manquants
        mock_fused = Mock()
        mock_fused.document = "vm_start(vm_name: string)"
        pipeline._retriever.retrieve.return_value = [mock_fused]

        pipeline._ephaistos.analyze_with_retry.return_value = EphaistosAnalysis(
            tool="vm_start",
            arguments={},
            missing_args=["vm_name"],
            confidence=0.85,
            reasoning="VM non specifiee",
            raw_response="{}"
        )

        pipeline._lyra.ask_clarification.return_value = LyraResponse(
            text="Quelle VM tu veux demarrer?",
            mentions_ephaistos=False,
            mentions_hestia=False
        )

        # Premier tour - clarification
        result1 = pipeline.process("demarre une VM")
        assert "vm_name" in result1.pending_args

        # Mock pour le deuxieme tour - args completes
        pipeline._ephaistos.extract_missing_args.return_value = EphaistosAnalysis(
            tool="vm_start",
            arguments={"vm_name": "preprod-09"},
            missing_args=[],
            confidence=0.95,
            reasoning="VM fournie",
            raw_response="{}"
        )

        pipeline._lyra.confirm_action.return_value = "Je demarre preprod-09?"

        # Deuxieme tour - completion
        result2 = pipeline.process("preprod-09")

        assert result2.tool_call is not None
        assert result2.tool_call["arguments"]["vm_name"] == "preprod-09"
        assert len(result2.pending_args) == 0

        # Verifier que l'action en attente est clear
        assert pipeline.get_pending_action() is None

    def test_multi_step_clarification(self, pipeline_with_mocks):
        """Test: clarification en plusieurs etapes."""
        pipeline = pipeline_with_mocks

        # Setup initial - 2 args manquants
        mock_fused = Mock()
        mock_fused.document = "vm_clone(source_vm: string, new_vm_name: string)"
        pipeline._retriever.retrieve.return_value = [mock_fused]

        pipeline._ephaistos.analyze_with_retry.return_value = EphaistosAnalysis(
            tool="vm_clone",
            arguments={},
            missing_args=["source_vm", "new_vm_name"],
            confidence=0.85,
            reasoning="VMs non specifiees",
            raw_response="{}"
        )

        pipeline._lyra.ask_clarification.return_value = LyraResponse(
            text="C'est quelle VM source?",
            mentions_ephaistos=False,
            mentions_hestia=False
        )

        # Tour 1 - demande initiale
        result1 = pipeline.process("clone ma VM")
        assert len(result1.pending_args) == 2

        # Tour 2 - donne source_vm, manque new_vm_name
        pipeline._ephaistos.extract_missing_args.return_value = EphaistosAnalysis(
            tool="vm_clone",
            arguments={"source_vm": "preprod-09"},
            missing_args=["new_vm_name"],
            confidence=0.90,
            reasoning="Source fournie, nom manquant",
            raw_response="{}"
        )

        result2 = pipeline.process("preprod-09")
        assert "new_vm_name" in result2.pending_args
        assert "source_vm" not in result2.pending_args

        # Tour 3 - donne new_vm_name
        pipeline._ephaistos.extract_missing_args.return_value = EphaistosAnalysis(
            tool="vm_clone",
            arguments={"source_vm": "preprod-09", "new_vm_name": "test-clone"},
            missing_args=[],
            confidence=0.95,
            reasoning="Tous args fournis",
            raw_response="{}"
        )

        pipeline._lyra.confirm_action.return_value = "Je clone preprod-09 vers test-clone?"

        result3 = pipeline.process("test-clone")
        # Tour 3 declenche la question COW (linked non specifie)
        assert "_linked_choice" in result3.pending_args or len(result3.pending_args) == 0,             f"Tour 3: attendu COW question ou pret a executer, got: {result3.response[:100]}"

        if "_linked_choice" in result3.pending_args:
            # Tour 4: repondre au choix COW
            result4 = pipeline.process("1")  # copie complete
            assert len(result4.pending_args) == 0
            assert result4.tool_call is not None
            assert result4.tool_call["arguments"]["source_vm"] == "preprod-09"
            assert result4.tool_call["arguments"]["new_vm_name"] == "test-clone"
        else:
            # Pas de question COW (linked deja dans args) - verifier le tool_call
            assert result3.tool_call["arguments"]["source_vm"] == "preprod-09"
            assert result3.tool_call["arguments"]["new_vm_name"] == "test-clone"


class TestKnowledgeWorkflow:
    """Tests du workflow knowledge."""

    def test_knowledge_with_context(self, pipeline_with_mocks):
        """Test question avec contexte RAG."""
        pipeline = pipeline_with_mocks

        # Configurer detect_query_type pour retourner KNOWLEDGE
        pipeline._retriever.detect_query_type.return_value = QueryType.KNOWLEDGE

        # Mock RAG results
        mock_fused = Mock()
        mock_fused.document = "vm_start demarre une machine virtuelle KVM"
        pipeline._retriever.retrieve.return_value = [mock_fused]

        # Mock LYRA response
        pipeline._lyra.answer_knowledge.return_value = LyraResponse(
            text="vm_start permet de demarrer une machine virtuelle KVM.",
            mentions_ephaistos=True,
            mentions_hestia=False
        )

        # Process
        result = pipeline.process("c'est quoi vm_start")

        assert result.query_type == QueryType.KNOWLEDGE
        assert "vm_start" in result.response.lower() or "demarrer" in result.response.lower()
        assert result.tool_call is None

    def test_knowledge_no_context(self, pipeline_with_mocks):
        """Test question sans contexte RAG."""
        pipeline = pipeline_with_mocks

        # Configurer detect_query_type pour retourner KNOWLEDGE
        pipeline._retriever.detect_query_type.return_value = QueryType.KNOWLEDGE

        # Mock RAG vide
        pipeline._retriever.retrieve.return_value = []

        # Mock LYRA response
        pipeline._lyra.answer_knowledge.return_value = LyraResponse(
            text="Je n'ai pas d'information precise sur ce sujet.",
            mentions_ephaistos=False,
            mentions_hestia=False
        )

        # Process
        result = pipeline.process("comment fonctionne xyz")

        assert result.query_type == QueryType.KNOWLEDGE


class TestExecution:
    """Tests de l'execution via HESTIA."""

    def test_execute_success(self, pipeline_with_mocks):
        """Test execution reussie."""
        pipeline = pipeline_with_mocks

        # Mock HESTIA
        pipeline._hestia.execute.return_value = ExecutionResult(
            success=True,
            content='{"status": "running", "ip": "192.168.122.146"}',
            duration_ms=1500.0
        )

        # Mock LYRA format
        pipeline._lyra.format_result.return_value = LyraResponse(
            text="C'est fait, preprod-09 est demarree. Son IP est 192.168.122.146.",
            mentions_ephaistos=False,
            mentions_hestia=True
        )

        # Execute
        result = pipeline.execute_action(
            tool_name="vm_start",
            arguments={"vm_name": "preprod-09"},
            user_query="demarre preprod-09"
        )

        assert result.executed
        assert result.execution_result.success
        assert "192.168.122.146" in result.response or "demarree" in result.response.lower()

    def test_execute_failure(self, pipeline_with_mocks):
        """Test execution echouee."""
        pipeline = pipeline_with_mocks

        # Mock HESTIA failure
        pipeline._hestia.execute.return_value = ExecutionResult(
            success=False,
            content="",
            error="VM not found: nonexistent-vm",
            duration_ms=500.0
        )

        # Mock LYRA error format
        pipeline._lyra.format_error.return_value = LyraResponse(
            text="Il y a eu un probleme: la VM n'existe pas.",
            mentions_ephaistos=False,
            mentions_hestia=True
        )

        # Execute
        result = pipeline.execute_action(
            tool_name="vm_start",
            arguments={"vm_name": "nonexistent-vm"},
            user_query="demarre nonexistent-vm"
        )

        assert result.executed
        assert not result.execution_result.success
        assert result.error is not None


class TestDangerousActions:
    """Tests des actions dangereuses."""

    def test_is_dangerous_vm_destroy(self, pipeline_with_mocks):
        """vm_destroy est dangereuse."""
        pipeline = pipeline_with_mocks
        pipeline._hestia.is_dangerous_tool.return_value = True

        assert pipeline.is_dangerous_action("vm_destroy")

    def test_is_dangerous_backup_restore(self, pipeline_with_mocks):
        """backup_restore est dangereuse."""
        pipeline = pipeline_with_mocks
        pipeline._hestia.is_dangerous_tool.return_value = True

        assert pipeline.is_dangerous_action("backup_restore")

    def test_is_not_dangerous_vm_start(self, pipeline_with_mocks):
        """vm_start n'est pas dangereuse."""
        pipeline = pipeline_with_mocks
        pipeline._hestia.is_dangerous_tool.return_value = False

        assert not pipeline.is_dangerous_action("vm_start")


class TestSessionManagement:
    """Tests de la gestion de session."""

    def test_session_history(self, pipeline_with_mocks):
        """Test historique de session."""
        pipeline = pipeline_with_mocks

        # Mock pour deux tours
        mock_fused = Mock()
        mock_fused.document = "vm_status(vm_name?: string)"
        pipeline._retriever.retrieve.return_value = [mock_fused]

        pipeline._ephaistos.analyze_with_retry.return_value = EphaistosAnalysis(
            tool="vm_status",
            arguments={},
            missing_args=[],
            confidence=0.90,
            reasoning="Lister toutes les VMs",
            raw_response="{}"
        )

        pipeline._lyra.confirm_action.return_value = "Je liste les VMs?"

        # Deux tours
        pipeline.process("liste les VMs")
        pipeline.process("status")

        history = pipeline.get_session_history()
        assert len(history) == 2

    def test_clear_session(self, pipeline_with_mocks):
        """Test effacement de session."""
        pipeline = pipeline_with_mocks

        # Setup avec pending action
        pipeline._session.set_pending_action(
            tool_name="vm_clone",
            known_args={},
            missing_args=["source_vm"],
            clarification_question="Quelle VM?"
        )

        assert pipeline.get_pending_action() is not None

        # Clear
        pipeline.clear_session()

        assert pipeline.get_pending_action() is None
        assert len(pipeline.get_session_history()) == 0


class TestMetrics:
    """Tests des metriques."""

    def test_get_metrics(self, pipeline_with_mocks):
        """Test recuperation des metriques."""
        pipeline = pipeline_with_mocks

        # Mock stats
        pipeline._model_manager.get_stats.return_value = {
            "ephaistos_calls": 5,
            "lyra_calls": 3,
            "total_calls": 8
        }

        pipeline._hestia.get_metrics.return_value = {
            "total_executions": 10,
            "success_rate": 0.9
        }

        metrics = pipeline.get_metrics()

        assert "models" in metrics
        assert "hestia" in metrics
        assert "session" in metrics
        assert metrics["models"]["total_calls"] == 8


class TestProcessWithContext:
    """Tests de process_with_context."""

    def test_restore_pending_action(self, pipeline_with_mocks):
        """Test restauration d'action en attente."""
        pipeline = pipeline_with_mocks

        # Mock pour le traitement
        pipeline._ephaistos.extract_missing_args.return_value = EphaistosAnalysis(
            tool="vm_start",
            arguments={"vm_name": "test-vm"},
            missing_args=[],
            confidence=0.95,
            reasoning="Args complets",
            raw_response="{}"
        )

        pipeline._lyra.confirm_action.return_value = "Je demarre test-vm?"

        # Process avec contexte
        result = pipeline.process_with_context(
            query="test-vm",
            pending_action={
                "tool_name": "vm_start",
                "known_args": {},
                "missing_args": ["vm_name"],
                "question": "Quelle VM?"
            }
        )

        assert result.tool_call is not None
        assert result.tool_call["name"] == "vm_start"
