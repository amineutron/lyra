"""Logique pure du vocal via le demon : texte parle et confirmations."""

import pytest

from lyra.client.vocal_text import (
    clean_for_speech,
    interpret_confirmation,
    spoken_text,
)


@pytest.mark.parametrize("transcript,danger,expected", [
    ("oui", False, "oui"),
    ("Oui, vas-y", False, "oui"),
    ("ouais", False, "oui"),
    ("d'accord", False, "oui"),
    ("non", False, "non"),
    ("Non merci, annule", False, "non"),
    ("pas du tout", False, "non"),
    ("pas oui", False, "non"),          # negation prioritaire
    ("modifier", False, "m"),
    ("", False, None),                  # silence : jamais une confirmation
    ("   ", False, None),
    ("euh peut-etre", False, None),
    ("hmm", False, None),
    # action dangereuse : confirmation explicite uniquement
    ("oui", True, "oui"),
    ("confirme", True, "oui"),
    ("ok", True, None),
    ("vas-y", True, None),
    ("d'accord", True, None),
    ("non", True, "non"),
])
def test_interpret_confirmation(transcript, danger, expected):
    assert interpret_confirmation(transcript, danger=danger) == expected


def test_interpret_confirmation_never_returns_empty():
    for text in ("", "?", "...", "bof"):
        assert interpret_confirmation(text) is None
        assert interpret_confirmation(text, danger=True) is None


@pytest.mark.parametrize("raw,expected", [
    ("\x1b[31mAttention\x1b[0m", "Attention"),
    ("[+] VM demarree", "VM demarree"),
    ("vm_stop sur dev-01. C'est bon ? [O/n]", "vm_stop sur dev-01. C'est bon ?"),
    ("a   b\n c", "a b c"),
    ("", ""),
])
def test_clean_for_speech(raw, expected):
    assert clean_for_speech(raw) == expected


def test_clean_for_speech_truncates_on_word_boundary():
    out = clean_for_speech("mot " * 200, limit=50)
    assert out.endswith("...")
    assert len(out) <= 54


@pytest.mark.parametrize("message,expected", [
    ({"type": "output", "kind": "lyra", "text": "Salut"}, "Salut"),
    ({"type": "output", "kind": "lyra_tag", "text": "ok ?"}, "ok ?"),
    ({"type": "output", "kind": "tool_result", "text": "fait"}, "fait"),
    ({"type": "output", "kind": "info", "text": "debug"}, None),
    ({"type": "output", "kind": "tool_call", "tool": "x"}, None),
    ({"type": "output", "kind": "lyra", "text": "  "}, None),
    ({"type": "progress", "step": "x"}, None),
])
def test_spoken_text(message, expected):
    assert spoken_text(message) == expected
