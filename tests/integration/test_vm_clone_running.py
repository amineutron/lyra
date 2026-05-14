"""
Test d'integration pour le workflow de clone avec VM running.

Verifie que la detection de VM en cours d'execution fonctionne
dans le workflow multi-tour (clarification step-by-step).
"""

import pytest
from unittest.mock import Mock
from dataclasses import dataclass

from lyra.core.pipeline import Pipeline
from lyra.core.config import RAGConfig
from lyra.models.ephaistos import EphaistosAnalysis
from lyra.models.lyra_voice import LyraResponse
from lyra.models.intent_classifier import Intent, ClassificationResult
from lyra.hestia.executor import ExecutionResult


@pytest.fixture
def pipeline_with_mocks():
    """Pipeline avec tous les composants mockes."""
    config = RAGConfig()
    config.llm = {"base_url": "http://localhost:11434", "timeout": 120}
    config.mcp = {"servers": {}}

    pipeline = Pipeline(config)

    # Mock les composants
    # Fournir un doc minimal pour que la pipeline passe a EPHAISTOS
    mock_spec = Mock()
    mock_spec.document = "vm_clone(source_vm: string, new_vm_name: string) - Clone une VM KVM"
    mock_spec.metadata = {"name": "fedora.vm_clone", "server": "fedora"}
    mock_spec.score = 0.9

    pipeline._retriever = Mock()
    pipeline._retriever.retrieve.return_value = [mock_spec]

    pipeline._model_manager = Mock()
    pipeline._ephaistos = Mock()
    pipeline._lyra = Mock()
    pipeline._hestia = Mock()
    pipeline._intent_classifier = Mock()

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

    return pipeline


def test_vm_clone_running_detection_multiturn(pipeline_with_mocks):
    """
    Test le workflow complet de clone avec detection de VM running
    dans le cas multi-tour (clarification step-by-step).

    Scenario:
    1. User: "clone preprod01" (avec typo)
    2. Pipeline: detecte typo, demande confirmation source
    3. User: "preprod-01" (correction)
    4. Pipeline: demande destination
    5. User: "clone4test"
    6. Pipeline: DOIT detecter que preprod-01 est running et proposer 3 options
    """
    pipeline = pipeline_with_mocks

    # ============================================================
    # Configuration des mocks
    # ============================================================

    # Intent classifier: toujours "demande"
    pipeline._intent_classifier.classify.return_value = ClassificationResult(
        intent=Intent.DEMANDE,
        confidence=0.95,
        raw_response="Action MCP"
    )

    # Mock LYRA pour acknowledgements et clarifications
    pipeline._lyra.generate_acknowledgement.return_value = None

    # Mock HESTIA pour vm_status
    def mock_execute(tool_name, arguments=None, **kwargs):
        """Mock de l'executeur Hestia."""
        if arguments is None:
            arguments = {}

        # get_all_vms ou vm_status sans vm_name
        if "get_all_vms" in tool_name or (tool_name == "fedora.vm_status" and not arguments.get("vm_name")):
            content = "preprod-01  running  192.168.122.245  22\npreprod-02  stopped  -  -\n"
            return ExecutionResult(success=True, content=content)

        # vm_status avec vm_name=preprod-01 (RUNNING)
        elif tool_name == "fedora.vm_status" and arguments.get("vm_name") == "preprod-01":
            content = (
                "  ========================================\n"
                "    VM: preprod-01\n"
                "  ========================================\n\n"
                "  Status:  en cours d'execution\n"
                "  IP:      192.168.122.245\n"
                "  SSH:     (22)\n"
            )
            return ExecutionResult(success=True, content=content)

        # vm_status avec vm_name=preprod-02 (STOPPED)
        elif tool_name == "fedora.vm_status" and arguments.get("vm_name") == "preprod-02":
            content = (
                "  ========================================\n"
                "    VM: preprod-02\n"
                "  ========================================\n\n"
                "  Status:  Arretee\n"
                "  IP:      -\n"
            )
            return ExecutionResult(success=True, content=content)

        return ExecutionResult(success=False, content="Unknown tool")

    pipeline._hestia.execute = mock_execute

    # ============================================================
    # TOUR 1: "clone preprod01" (avec typo)
    # ============================================================

    # EPHAISTOS analyse Tour 1
    pipeline._ephaistos.analyze_with_retry.return_value = EphaistosAnalysis(
        tool="fedora.vm_clone",
        arguments={"source_vm": "preprod01"},  # avec typo
        missing_args=["new_vm_name"],
        confidence=0.8,
        reasoning="Clone VM",
        raw_response=""
    )

    result1 = pipeline.process("clone preprod01")

    # Verification Tour 1
    assert "preprod-01" in result1.response.lower(), "Tour 1: devrait suggerer preprod-01"
    assert result1.pending_args, "Tour 1: devrait avoir pending args"

    print(f"\n✅ TOUR 1: Typo detectee")
    print(f"   Response: {result1.response[:100]}...")

    # ============================================================
    # TOUR 2: "preprod-01" (correction source)
    # ============================================================

    # EPHAISTOS extract_missing_args Tour 2
    # L'utilisateur confirme "preprod-01", on demande maintenant new_vm_name
    pipeline._ephaistos.extract_missing_args.return_value = EphaistosAnalysis(
        tool="fedora.vm_clone",
        arguments={"source_vm": "preprod-01"},  # source corrigee
        missing_args=["new_vm_name"],  # encore besoin du nom destination
        confidence=0.9,
        reasoning="Source confirmee",
        raw_response=""
    )

    # LYRA demande le nom destination
    pipeline._lyra.ask_clarification.return_value = LyraResponse(
        text="Quel nom veux-tu pour le clone ?",
        mentions_ephaistos=False,
        mentions_hestia=False
    )

    result2 = pipeline.process("preprod-01")

    # Verification Tour 2
    assert "nom" in result2.response.lower() or "clone" in result2.response.lower(), \
        "Tour 2: devrait demander le nom destination"

    print(f"\n✅ TOUR 2: Demande nom destination")
    print(f"   Response: {result2.response[:100]}...")

    # ============================================================
    # TOUR 3: "clone4test" (nom destination) - LE TEST CRITIQUE
    # ============================================================

    # EPHAISTOS extract_missing_args Tour 3: TOUS les arguments sont presents
    pipeline._ephaistos.extract_missing_args.return_value = EphaistosAnalysis(
        tool="fedora.vm_clone",
        arguments={
            "source_vm": "preprod-01",
            "new_vm_name": "clone4test"
        },
        missing_args=[],  # PLUS D'ARGUMENTS MANQUANTS
        confidence=0.95,
        reasoning="Arguments complets",
        raw_response=""
    )

    result3 = pipeline.process("clone4test")

    # ============================================================
    # VERIFICATION FINALE - LE TEST CRITIQUE
    # ============================================================

    print(f"\n{'='*70}")
    print("TOUR 3: Detection VM running (TEST CRITIQUE)")
    print(f"{'='*70}")
    print(f"\nResponse complete:\n{result3.response}")
    print(f"\n{'='*70}")

    # Le Tour 3 DOIT detecter que preprod-01 est running et proposer 3 options
    expected_phrases = [
        "en cours",  # "en cours d'execution"
        "arrêter",   # "arreter la VM"
        "option",    # "Options:"
        "1",         # Option 1
        "2",         # Option 2
        "3",         # Option 3
        "annuler"    # Option 3: Annuler
    ]

    found = []
    missing = []

    for phrase in expected_phrases:
        if phrase.lower() in result3.response.lower():
            found.append(phrase)
        else:
            missing.append(phrase)

    # Assertions
    assert "en cours" in result3.response.lower(), \
        f"CRITICAL: La detection de VM running ne fonctionne pas!\n" \
        f"Response: {result3.response[:300]}\n" \
        f"Phrases manquantes: {missing}"

    assert "option" in result3.response.lower(), \
        f"CRITICAL: Le menu d'options n'apparait pas!\n" \
        f"Response: {result3.response[:300]}"

    assert "1" in result3.response and "2" in result3.response and "3" in result3.response, \
        f"CRITICAL: Les 3 options ne sont pas toutes presentes!\n" \
        f"Response: {result3.response[:300]}"

    print(f"\n✅ ✅ ✅ TEST REUSSI ✅ ✅ ✅")
    print(f"\nLa detection de VM running fonctionne correctement!")
    print(f"Le menu avec 3 options s'affiche comme attendu.")
    print(f"\nPhrases trouvees: {found}")


def test_vm_clone_stopped_vm_no_menu(pipeline_with_mocks):
    """
    Test que le menu d'options n'apparait PAS si la VM est arretee.
    """
    pipeline = pipeline_with_mocks

    # Intent classifier
    pipeline._intent_classifier.classify.return_value = ClassificationResult(
        intent=Intent.DEMANDE,
        confidence=0.95,
        raw_response="Action MCP"
    )

    pipeline._lyra.generate_acknowledgement.return_value = None

    # Mock HESTIA: preprod-02 est ARRETEE
    def mock_execute(tool_name, arguments=None, **kwargs):
        if arguments is None:
            arguments = {}
        if "get_all_vms" in tool_name or (tool_name == "fedora.vm_status" and not arguments.get("vm_name")):
            content = "preprod-01  running  192.168.122.245  22\npreprod-02  stopped  -  -\n"
            return ExecutionResult(success=True, content=content)

        elif tool_name == "fedora.vm_status" and arguments.get("vm_name") == "preprod-02":
            content = (
                "  ========================================\n"
                "    VM: preprod-02\n"
                "  ========================================\n\n"
                "  Status:  Arretee\n"
                "  IP:      -\n"
            )
            return ExecutionResult(success=True, content=content)

        return ExecutionResult(success=False, content="Unknown")

    pipeline._hestia.execute = mock_execute

    # Analyse directe avec tous les arguments
    pipeline._ephaistos.analyze_with_retry.return_value = EphaistosAnalysis(
        tool="fedora.vm_clone",
        arguments={
            "source_vm": "preprod-02",
            "new_vm_name": "test-clone"
        },
        missing_args=[],
        confidence=0.95,
        reasoning="Clone VM arretee",
        raw_response=""
    )

    result = pipeline.process("clone preprod-02 en test-clone")

    # Verification: PAS de menu d'options car VM arretee
    assert "option" not in result.response.lower(), \
        "Ne devrait PAS afficher le menu d'options si la VM est arretee"

    assert "en cours d'exécution" not in result.response.lower(), \
        "Ne devrait PAS indiquer que la VM est running si elle est arretee"

    print(f"\n✅ TEST REUSSI: Pas de menu pour VM arretee")
    print(f"   Response: {result.response[:150]}...")
