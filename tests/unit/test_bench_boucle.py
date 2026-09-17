"""Generation des configurations de la boucle d'amelioration (logique pure)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from bench_boucle import configurations  # noqa: E402


class TestConfigurations:
    def test_sans_socle_commence_par_le_defaut(self):
        c = configurations(False, ("a", "b"))
        assert c == [(), ("a",), ("b",), ("a", "b"), ("a", "b")]

    def test_socle_present_partout(self):
        c = configurations(False, ("a", "b"), socle=("s",))
        assert all(cfg[:1] == ("s",) for cfg in c)
        assert c[0] == ("s",)
        assert ("s", "a", "b") in c

    def test_rapide_sans_paires(self):
        c = configurations(True, ("a", "b", "c"), socle=("s",))
        assert len(c) == 1 + 3 + 1

    def test_compte_complet(self):
        """1 socle + 5 seules + 10 paires + toutes = 17."""
        assert len(configurations(False, ("a", "b", "c", "d", "e"), socle=("s",))) == 17
