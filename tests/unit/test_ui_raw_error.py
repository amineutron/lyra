"""Tests unitaires pour format_raw_error (detail technique du panneau ERREUR)."""

import pytest

from modules.ui import format_raw_error


class TestFormatRawError:
    def test_vide_retourne_vide(self):
        assert format_raw_error("") == ""
        assert format_raw_error(None or "") == ""
        assert format_raw_error("   \n  ") == ""

    def test_erreur_simple_conservee(self):
        raw = "backup-list.sh: ligne 201: BORG_PASSPHRASE_FILE : variable sans liaison"
        assert format_raw_error(raw) == raw

    def test_deja_dans_la_reponse_skip(self):
        raw = "Erreur: fichier introuvable"
        response = "Oups. Erreur: fichier introuvable. On reessaie ?"
        assert format_raw_error(raw, response=response) == ""

    def test_garde_les_dernieres_lignes(self):
        raw = "\n".join(f"ligne {i}" for i in range(1, 11))
        result = format_raw_error(raw, max_lines=3)
        assert result == "ligne 8\nligne 9\nligne 10"

    def test_lignes_vides_ignorees(self):
        raw = "cause reelle\n\n\n   \n"
        assert format_raw_error(raw, max_lines=3) == "cause reelle"

    def test_troncature_max_chars(self):
        raw = "x" * 500
        result = format_raw_error(raw, max_chars=100)
        assert result.startswith("...")
        assert len(result) == 103  # "..." + 100 derniers chars

    @pytest.mark.parametrize("raw,expected_in", [
        ("a\nb\nc\nd", "d"),                       # la fin est gardee (cause en fin de stderr)
        ("Traceback...\nValueError: boom", "ValueError: boom"),
    ])
    def test_fin_de_stderr_prioritaire(self, raw, expected_in):
        assert expected_in in format_raw_error(raw)
