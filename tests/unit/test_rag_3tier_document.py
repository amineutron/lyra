"""Le document capabilities ne duplique pas les paraphrases (regression 2026-09-18)."""

import pytest

pytest.importorskip("chromadb")
from lyra.rag_enhanced.rag_3tier import document_capabilities  # noqa: E402


def test_paraphrases_une_seule_fois():
    entry = {"capabilities": "Regle le volume | Utilise pour: régler le volume à X. monte le son",
             "use_cases": "régler le volume à X. monte le son"}
    doc = document_capabilities(entry)
    assert doc.count("régler le volume à X") == 1 and doc.count("Utilise pour") == 1


def test_sans_paraphrase_dans_capabilities_on_les_ajoute():
    assert document_capabilities({"capabilities": "Regle le volume", "use_cases": "monte le son"}) == \
        "Regle le volume | Utilise pour: monte le son"


def test_sans_use_cases():
    assert document_capabilities({"capabilities": "Regle le volume", "use_cases": ""}) == "Regle le volume"
