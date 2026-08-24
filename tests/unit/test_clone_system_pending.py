"""Regression 2026-08-14 (batterie neutroncore) : le multi-tour du clone
systeme ne capturait pas la reponse utilisateur.

Conversation reelle :
  "Fais une VM clone systeme" -> demande le nom (OK)
  "Test-vm"                   -> EPHAISTOS 0.5b hallucine ("snapshots preprod-12")
  "La source est mon pc et le nom est test-new-vm" -> encore rate

Le clone systeme n'a qu'UN argument (name, la source est l'hote) :
l'extraction doit etre deterministe, pas confiee au LLM.
"""
import pytest

from lyra.rules.vm import extract_clone_system_name


@pytest.mark.parametrize("reponse,attendu", [
    # nom brut (le cas le plus naturel)
    ("Test-vm", "test-vm"),
    ("test-new-vm", "test-new-vm"),
    ("  neutron-light  ", "neutron-light"),
    # marqueur "le nom est X" (avec ou sans mention de la source)
    ("le nom est test-new-vm", "test-new-vm"),
    ("La source est mon pc et le nom est test-new-vm", "test-new-vm"),
    ("le nom de la machine est test-vm", "test-vm"),
    ("le nom de la nouvelle vm est clone-pc", "clone-pc"),
    # variantes d'appellation
    ("nomme-la demo-vm", "demo-vm"),
    ("appelle-la neutron-clone", "neutron-clone"),
    ("c'est test-vm", "test-vm"),
    ("ce sera portable-01", "portable-01"),
])
def test_nom_extrait(reponse, attendu):
    assert extract_clone_system_name(reponse) == attendu


@pytest.mark.parametrize("reponse", [
    # reponses qui ne contiennent PAS de nom exploitable
    "oui", "ok", "non", "mon pc", "la source est mon pc",
    "je sais pas", "",
])
def test_pas_de_nom(reponse):
    assert extract_clone_system_name(reponse) is None
