"""examples_map de scripts/reindex_mcp_rag_optimized.py (Lyra #24).

Chaque outil reel (docs/user/MCP_TOOLS.md, genere depuis les serveurs) doit avoir
des exemples indexes, et aucun exemple ne doit recopier une phrase d'un jeu de
test : le banc mesurerait alors la memoire de l'index, pas la comprehension.
"""
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "tests"))

from cases_hors_regles import TESTS_HORS_REGLES  # noqa: E402
from cases_hors_regles_2 import TESTS_HORS_REGLES_2  # noqa: E402
from cases_hors_regles_3 import TESTS_HORS_REGLES_3  # noqa: E402
from cases_hors_regles_4 import TESTS_HORS_REGLES_4  # noqa: E402
from cases_hors_regles_5 import TESTS_HORS_REGLES_5  # noqa: E402
from reindex_mcp_rag_optimized import generate_french_examples  # noqa: E402

from lyra.models.ephaistos_exp import normaliser  # noqa: E402

OUTILS = sorted(set(re.findall(r"^\| `([a-z]+\.[a-z0-9_]+)`", (REPO / "docs/user/MCP_TOOLS.md").read_text(), re.M)))


def test_catalogue_lu():
    assert len(OUTILS) >= 80


@pytest.mark.parametrize("outil", OUTILS)
def test_chaque_outil_a_des_exemples(outil):
    exemples = generate_french_examples(outil, "")
    assert len(exemples) >= 3, f"{outil} : {len(exemples)} exemple(s)"


def test_aucun_exemple_ne_recopie_un_jeu_de_test():
    jeux = TESTS_HORS_REGLES + TESTS_HORS_REGLES_2 + TESTS_HORS_REGLES_3 + TESTS_HORS_REGLES_4 + TESTS_HORS_REGLES_5
    phrases_test = {" ".join(normaliser(cas[2])) for cas in jeux}
    fuites = [
        (outil, ex) for outil in OUTILS for ex in generate_french_examples(outil, "")
        if " ".join(normaliser(ex)) in phrases_test
    ]
    assert not fuites, fuites


@pytest.mark.parametrize("brut, attendu", [
    ("Exécute une commande dans une VM via SSH ⚠️ ATTENTION: Opération potentiellement destructive!",
     "Exécute une commande dans une VM via SSH"),
    ("Restaure un backup (ATTENTION: opération destructive!) ⚠️ ATTENTION: Opération potentiellement destructive!",
     "Restaure un backup"),
    ("Arrête une VM KVM proprement (ou force l'arrêt avec --force)",
     "Arrête une VM KVM proprement (ou force l'arrêt avec --force)"),
    ("", ""),
])
def test_description_indexable_retire_l_avertissement(brut, attendu):
    from reindex_mcp_rag_optimized import description_indexable
    assert description_indexable(brut) == attendu


def test_limites_par_defaut_de_production():
    """Une reindexation sans variable d'environnement reproduit l'index de production (6 x 16)."""
    import reindex_mcp_rag_optimized as r
    assert (r.TRIGGERS_MAX_DEFAUT, r.VARIANTES_MAX_DEFAUT) == (6, 16)
