"""Invariants des cartes de mots (lyra/models/cartes.py) : des mots, jamais des phrases."""
import re

from lyra.models import cartes

TABLES = [n for n in dir(cartes) if n.isupper() and not n.startswith("__")]


def test_les_cles_sont_des_mots_simples():
    for nom in TABLES:
        table = getattr(cartes, nom)
        if not isinstance(table, dict):
            continue
        for cle in table:
            assert re.fullmatch(r"[a-z0-9]+", cle), f"{nom}: cle '{cle}' n'est pas un mot normalise"


def test_les_cibles_sont_des_tuples_de_chaines_non_vides():
    for nom in TABLES:
        table = getattr(cartes, nom)
        if not isinstance(table, dict):
            continue
        for cle, cibles in table.items():
            if isinstance(cibles, str):   # table de correspondance simple (modes ambilight)
                assert cibles, f"{nom}[{cle}]"
                continue
            assert isinstance(cibles, tuple) and cibles, f"{nom}[{cle}]"
            assert all(isinstance(c, str) and c for c in cibles), f"{nom}[{cle}]"


def test_aucune_table_vide():
    assert len(TABLES) >= 25
    for nom in TABLES:
        assert getattr(cartes, nom), nom
