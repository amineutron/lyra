"""Regressions du 2026-08-14 (batterie de test neutroncore) :
- "comment vas tu ?" classe demande -> fallback "je n'ai pas compris"
- "c'est quoi arch-base" classe info -> hallucination LYRA
"""
import pytest

from lyra.models.intent_classifier import _SMALLTALK_RE, _VM_QUESTION_RE, _KNOWLEDGE_RE, _ascii_lower
from lyra.rules.vm import detect


@pytest.mark.parametrize("phrase", [
    "comment vas tu ?", "Comment ça va", "ca va bien ?", "salut", "merci beaucoup",
    "quoi de neuf", "qui es-tu ?",
])
def test_smalltalk_detecte(phrase):
    assert _SMALLTALK_RE.match(_ascii_lower(phrase)), phrase


@pytest.mark.parametrize("phrase", [
    "liste mes vms", "c'est quoi vm_clone", "demarre arch-base",
])
def test_smalltalk_ne_capture_pas_les_demandes(phrase):
    assert not _SMALLTALK_RE.match(_ascii_lower(phrase)), phrase


@pytest.mark.parametrize("phrase,attendu", [
    ("c'est quoi arch-base", True),
    ("qu'est-ce que electron-backup-test", True),
    ("c'est quoi la vm fedora-base", True),
    ("c'est quoi vm_clone", False),      # nom d'outil (underscore) = info
    ("c'est quoi le backup", False),
])
def test_vm_question(phrase, attendu):
    assert bool(_VM_QUESTION_RE.search(_ascii_lower(phrase))) == attendu, phrase


def test_vm_question_prioritaire_sur_knowledge():
    # les deux regex matchent "c'est quoi arch-base" ; l'ordre dans classify()
    # doit donner la priorite a vm_question (teste ici que knowledge matche
    # aussi, pour documenter pourquoi l'ordre compte)
    q = _ascii_lower("c'est quoi arch-base")
    assert _VM_QUESTION_RE.search(q) and _KNOWLEDGE_RE.search(q)


def test_regle_vm_status_cest_quoi():
    r = detect("c'est quoi arch-base")
    assert r is not None and r.tool == "fedora.vm_status"
    assert r.arguments == {"vm_name": "arch-base", "detailed": True}
    assert detect("c'est quoi vm_clone") is None or detect("c'est quoi vm_clone").tool != "fedora.vm_status"


@pytest.mark.parametrize("phrase", [
    "eteint neutron-template-05", "eteind neutron-template-05",
    "eteins neutron-template-05", "eteindre la vm arch-base",
])
def test_vm_stop_variantes_eteindre(phrase):
    r = detect(phrase)
    assert r is not None and r.tool == "fedora.vm_stop", phrase


@pytest.mark.parametrize("phrase", [
    "eteins les lumieres", "eteins la tv", "eteins tout",
])
def test_vm_stop_ne_capture_pas_domotique(phrase):
    r = detect(phrase)
    assert r is None or r.tool != "fedora.vm_stop", phrase


@pytest.mark.parametrize("phrase", ["creer une vm", "cree une nouvelle machine virtuelle"])
def test_creer_une_vm_route_vers_clone(phrase):
    r = detect(phrase)
    assert r is not None and r.tool == "fedora.vm_clone", phrase
    assert "source_vm" in r.missing_args


@pytest.mark.parametrize("phrase", ["fait un clone systeme", "clone le systeme", "duplique le system"])
def test_clone_systeme_sans_nom_interactif(phrase):
    r = detect(phrase)
    assert r is not None and r.tool == "fedora.vm_clone_system", phrase
    assert r.missing_args == ["name"]


@pytest.mark.parametrize("phrase,nom", [
    ("clone systeme en test-bureau", "test-bureau"),
    ("clone le systeme nomme vm-transportable", "vm-transportable"),
    ("fais un clone systeme appele demo-pc", "demo-pc"),
])
def test_clone_systeme_avec_nom(phrase, nom):
    r = detect(phrase)
    assert r.tool == "fedora.vm_clone_system" and r.arguments == {"name": nom}
