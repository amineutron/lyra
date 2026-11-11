"""Correction "m" au prompt de confirmation : parsing et liste blanche."""
import pytest

from lyra.daemon.actions import _modifier_arguments
from lyra.daemon.modify import ModifyError, is_modify_answer, parse_modification


@pytest.mark.parametrize("reponse", ["m", "M", " modifier ", "modify", "edit"])
def test_reponses_modify(reponse):
    assert is_modify_answer(reponse)


@pytest.mark.parametrize("reponse", ["", "o", "oui", "n", "non", "mm"])
def test_reponses_non_modify(reponse):
    assert not is_modify_answer(reponse)


@pytest.mark.parametrize("saisie,attendu", [
    ("vm_name=test-2", {"vm_name": "test-2", "n": 3}),
    ("vm_name=test-2 n=5", {"vm_name": "test-2", "n": 5}),
    ('vm_name="vm un"', {"vm_name": "vm un", "n": 3}),
])
def test_modification_valide(saisie, attendu):
    courant = {"vm_name": "test-1", "n": 3}
    assert parse_modification(saisie, courant) == attendu
    assert courant == {"vm_name": "test-1", "n": 3}  # pas de mutation


def test_valeur_nue_si_un_seul_argument():
    assert parse_modification("preprod-09", {"vm_name": "x"}) == {"vm_name": "preprod-09"}


def test_valeur_nue_refusee_si_plusieurs_arguments():
    with pytest.raises(ModifyError):
        parse_modification("preprod-09", {"a": "1", "b": "2"})


@pytest.mark.parametrize("saisie", [
    "", "   ", "autre=x", "vm_name=", "vm_name=a;rm -rf /", "vm_name=$(id)",
    "vm_name=a|b", "vm_name=`x`", "vm_name=-rf", "vm_name=../etc",
    "vm_name=" + "a" * 201, "n=abc", 'vm_name="oups',
])
def test_modification_refusee(saisie):
    with pytest.raises(ModifyError):
        parse_modification(saisie, {"vm_name": "test-1", "n": 3})


def test_bool_garde_son_type():
    assert parse_modification("force=non", {"force": True}) == {"force": False}
    with pytest.raises(ModifyError):
        parse_modification("force=peutetre", {"force": True})


class _Rui:
    def __init__(self, *reponses):
        self._r = list(reponses)
        self.warnings = []

    def ask(self, kind, prompt, payload=None):
        return self._r.pop(0)

    def warning(self, text):
        self.warnings.append(text)


def test_workflow_saisie_vide_annule():
    assert _modifier_arguments(_Rui(""), "fedora.vm_start", {"vm_name": "a"}) is None


def test_workflow_reessaie_apres_saisie_invalide():
    rui = _Rui("vm_name=a;b", "vm_name=b")
    assert _modifier_arguments(rui, "fedora.vm_start", {"vm_name": "a"}) == {"vm_name": "b"}
    assert len(rui.warnings) == 1


def test_workflow_abandon_apres_trois_saisies_invalides():
    rui = _Rui("x=1", "x=1", "x=1")
    assert _modifier_arguments(rui, "t", {"vm_name": "a"}) is None


def test_workflow_sans_argument():
    assert _modifier_arguments(_Rui(), "t", {}) is None
