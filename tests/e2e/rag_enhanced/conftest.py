"""Fixtures communes pour tests E2E RAG Enhanced."""

import pytest
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path

from lyra.rag_enhanced import EnhancedPipeline, EnhancedPipelineResult
from lyra.core.config import RAGConfig
from lyra.core.pipeline import QueryType, PipelineResult
from lyra.models.ephaistos import EphaistosAnalysis
from lyra.models.lyra_voice import LyraResponse
from lyra.hestia.executor import ExecutionResult


@pytest.fixture
def mock_config():
    """Configuration mockee pour tests E2E."""
    config = RAGConfig()
    config.llm = {"base_url": "http://localhost:11434", "timeout": 120}
    config.mcp = {"servers": {}}
    return config


@pytest.fixture
def mock_ephaistos_response():
    """Mock reponse EPHAISTOS typique."""
    def _mock_response(tool_name: str, **kwargs):
        return EphaistosAnalysis(
            tool_name=tool_name,
            arguments=kwargs,
            confidence=0.95,
            reasoning="Test E2E mock"
        )
    return _mock_response


@pytest.fixture
def mock_lyra_response():
    """Mock reponse LYRA typique."""
    def _mock_response(message: str):
        return LyraResponse(
            response=message,
            thinking="Test E2E mock"
        )
    return _mock_response


@pytest.fixture
def mock_hestia_execution():
    """Mock execution HESTIA."""
    def _mock_exec(success: bool = True, result: str = "OK"):
        return ExecutionResult(
            success=success,
            result=result,
            error=None if success else "Mock error"
        )
    return _mock_exec


@pytest.fixture
def enhanced_pipeline_with_mocks(mock_config, mock_ephaistos_response,
                                  mock_lyra_response, mock_hestia_execution):
    """Pipeline Enhanced avec mocks Ollama/MCP mais composants RAG Enhanced reels.

    Mocks:
    - Ollama (EPHAISTOS + LYRA)
    - MCP execution (HESTIA)

    Reels:
    - SlangNormalizer
    - SynonymExpander
    - ContextInjector
    - ConfidenceCascader
    - FeedbackLoop
    - RAG retrieval (si ChromaDB compatible)
    """
    # Créer config enhanced avec tous composants activés
    from lyra.rag_enhanced.config import RAGEnhancedConfig
    enhanced_config = RAGEnhancedConfig(enabled=True)
    enhanced_config.slang_normalizer.enabled = True
    enhanced_config.synonym_expander.enabled = True
    enhanced_config.context_injector.enabled = True
    enhanced_config.feedback_loop.enabled = True
    # RAG 3-tier disabled pour simplifier (ChromaDB mocké)
    enhanced_config.rag_3tier.enabled = False

    with patch('lyra.rag.semantic_retriever.SemanticRetriever.initialize'):
        with patch('lyra.rag_enhanced.rag_3tier.RAG3Tier.initialize'):
            pipeline = EnhancedPipeline(
                config=mock_config,
                enhanced_config=enhanced_config,
                enabled=True
            )

            # Initialiser d'abord (charge composants RAG Enhanced)
            # IMPORTANT: les mocks V2 doivent etre poses APRES initialize()
            # car initialize() appelle _pipeline_v2.initialize() qui reecrit les attributs
            pipeline.initialize()

            # Mocks V2 poses APRES initialize() pour ne pas etre ecrases
            from lyra.models.intent_classifier import Intent, ClassificationResult
            from lyra.rag.session_memory import SessionMemory

            pipeline._pipeline_v2._ephaistos = Mock()
            pipeline._pipeline_v2._ephaistos.analyze_with_retry = Mock(return_value=Mock(
                tool="fedora.vm_start",
                arguments={"vm_name": "test"},
                missing_args=[],
                confidence=0.95,
                reasoning="Mock",
                raw_response=""
            ))

            pipeline._pipeline_v2._lyra = Mock()
            pipeline._pipeline_v2._lyra.format_result = Mock(return_value=Mock(
                text="Mock response",
                mentions_ephaistos=False,
                mentions_hestia=False
            ))
            pipeline._pipeline_v2._lyra.generate_acknowledgement = Mock(return_value=None)
            pipeline._pipeline_v2._lyra.greet = Mock(return_value="Bonjour")

            pipeline._pipeline_v2._hestia = Mock()
            pipeline._pipeline_v2._hestia.execute = Mock(return_value=ExecutionResult(
                success=True,
                content="OK"
            ))

            pipeline._pipeline_v2._retriever = Mock()
            pipeline._pipeline_v2._retriever.retrieve = Mock(return_value=[])
            pipeline._pipeline_v2._retriever.detect_query_type = Mock(return_value=QueryType.ACTION)

            pipeline._pipeline_v2._intent_classifier = Mock()
            pipeline._pipeline_v2._intent_classifier.classify = Mock(return_value=ClassificationResult(
                intent=Intent.DEMANDE,
                confidence=0.95,
                raw_response='{"intent": "demande"}'
            ))

            pipeline._pipeline_v2._sessions["default"] = SessionMemory(max_turns=10)
            pipeline._pipeline_v2._rule_based_detect = lambda q: None

            # Creer WorkflowContext avec les mocks
            from lyra.core.workflows.context import WorkflowContext

            return pipeline


@pytest.fixture
def session_id():
    """Session ID unique pour tests."""
    return "test_session_e2e"
