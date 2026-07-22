"""
Tests pour le parsing de selection de phases de run_scene.py
"""

import pytest

from .run_scene import parse_phase_selection


class TestParsePhaseSelection:
    """Tests table-driven du parsing '--phases'."""

    @pytest.mark.parametrize("spec,expected", [
        ("3", [3]),
        ("0", [0]),
        ("2-4", [2, 3, 4]),
        ("0-5", [0, 1, 2, 3, 4, 5]),
        ("1,3,5", [1, 3, 5]),
        ("1, 3 , 5", [1, 3, 5]),
        ("2-3,5", [2, 3, 5]),
        ("3,1", [3, 1]),          # ordre preserve
        ("1,1,2", [1, 2]),        # doublons supprimes
    ])
    def test_valid_specs(self, spec, expected):
        assert parse_phase_selection(spec) == expected

    @pytest.mark.parametrize("spec", [
        "6",        # hors bornes
        "-1",       # negatif (parse comme plage invalide)
        "4-2",      # plage inversee
        "abc",      # non numerique
        "",         # vide
        "1..3",     # mauvais separateur
    ])
    def test_invalid_specs(self, spec):
        with pytest.raises(ValueError):
            parse_phase_selection(spec)
