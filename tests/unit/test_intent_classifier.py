"""Tests des overrides regex de l'IntentClassifier.

Regression 2026-07-29 : "c'est quoi vm_clone" etait classe "demande" par
Llama 1b -> fallback "je n'ai pas compris". Les questions de connaissance
explicites doivent etre routees "info" sans appel LLM.
"""

from unittest.mock import MagicMock

import pytest

from lyra.models.intent_classifier import IntentClassifier, Intent


@pytest.fixture
def classifier():
    """Classifier avec model_manager mocke : tout appel LLM fait echouer le test."""
    manager = MagicMock()
    manager.call_lyra.side_effect = AssertionError(
        "L'override regex aurait du repondre sans appel LLM"
    )
    return IntentClassifier(manager)


@pytest.mark.parametrize("query", [
    "c'est quoi vm_clone",
    "c est quoi le backup",
    "qu'est-ce que vm_snapshot",
    "comment fonctionne le RAG",
    "comment marche la sauvegarde",
    "comment cloner une vm",
    "a quoi sert vm_verify",
    "explique moi vm_export",
    "difference entre clone et snapshot",
])
def test_knowledge_questions_are_info(classifier, query):
    result = classifier.classify(query)
    assert result.intent == Intent.INFO
    assert result.raw_response == "regex:knowledge_pattern"


@pytest.mark.parametrize("query", [
    "demarre fedora-base",
    "clone preprod-09 en test-clone",
    "verifie la vm fedora-base",
    "allume les lumieres",
    "liste mes vms",
])
def test_action_verbs_are_demande(classifier, query):
    result = classifier.classify(query)
    assert result.intent == Intent.DEMANDE
    assert result.raw_response == "regex:demande_verb"
