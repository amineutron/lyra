"""Confirmation des actions du demon : la liste statique ET l'annotation destructiveHint.

Regression : un outil qu'un serveur MCP tiers annote destructiveHint n'obtenait que la
confirmation souple ([O/n], Entree = oui) et s'executait sans question avec -y.
"""
from types import SimpleNamespace as N

import pytest

from lyra.daemon import actions


def _v2(destructifs=()):
    hestia = N(is_dangerous_tool=lambda nom: nom in destructifs)
    return N(_hestia=hestia)


@pytest.mark.parametrize("nom, destructifs, attendu", [
    ("fedora.vm_destroy", (), True),          # liste statique
    ("stock.purger", ("stock.purger",), True),  # annotation du serveur
    ("stock.lister", ("stock.purger",), False),
])
def test_outil_dangereux(nom, destructifs, attendu):
    assert actions._outil_dangereux(_v2(destructifs), nom) is attendu


def test_executeur_en_panne_retombe_sur_la_liste_statique():
    def panne(nom):
        raise RuntimeError("serveur muet")
    v2 = N(_hestia=N(is_dangerous_tool=panne))
    assert actions._outil_dangereux(v2, "stock.purger") is False
    assert actions._outil_dangereux(v2, "fedora.vm_stop") is True


def test_sans_executeur():
    assert actions._outil_dangereux(N(), "fedora.vm_stop") is True
    assert actions._outil_dangereux(N(), "stock.purger") is False


def test_mode_performance_ne_saute_jamais_un_outil_annote(monkeypatch):
    monkeypatch.setattr(actions, "PERFORMANCE_TOOLS", frozenset({"stock.purger"}))
    assert actions._should_skip_confirmation("stock.purger", "performance", dangerous=True) is False
    assert actions._should_skip_confirmation("stock.purger", "performance", dangerous=False) is True


def test_invite_d_un_outil_annote():
    from lyra.daemon.remote_ui import build_confirm_prompt
    prompt, danger = build_confirm_prompt("stock.purger", {"lot": "a"}, True)
    assert danger is True and "DESTRUCTIVE" in prompt and "son serveur" in prompt


@pytest.mark.parametrize("nom", ["fedora.vm_destroy", "fedora.vm_stop"])
def test_le_verdict_ne_change_pas_les_outils_des_listes(nom):
    from lyra.daemon.remote_ui import build_confirm_prompt
    assert build_confirm_prompt(nom, {}, True) == build_confirm_prompt(nom, {})
    assert build_confirm_prompt(nom, {}, False) == build_confirm_prompt(nom, {})


def test_sans_verdict_rien_ne_change():
    from lyra.daemon.remote_ui import build_confirm_prompt
    assert build_confirm_prompt("stock.lister", {}) == ("Executer stock.lister ?", False)


def test_fonction_partagee_des_constantes():
    from lyra.core.constants import is_dangerous_with_annotations as f
    assert f("fedora.vm_stop") is True
    assert f("stock.purger") is False
    assert f("stock.purger", N(is_dangerous_tool=lambda n: True)) is True
    assert f("stock.purger", N(is_dangerous_tool=lambda n: 1)) is False   # seul True compte


def test_mode_sans_demon_meme_regle(monkeypatch):
    """main_rag (--standalone) : -y et le mode performance suivent le meme verdict."""
    import main_rag
    monkeypatch.setattr(main_rag, "PERFORMANCE_TOOLS", frozenset({"stock.purger"}))
    assert main_rag.should_skip_confirmation("stock.purger", "performance", True) is False
    assert main_rag.should_skip_confirmation("stock.purger", "performance", False) is True
    assert main_rag.should_skip_confirmation("fedora.vm_stop", "performance") is False
