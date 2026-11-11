"""Resolution des noms de VM dits a voix haute ("test vm" -> "test-vm")."""

import pytest

from lyra.core import validation
from lyra.core.validation import resolve_vm_name, validate_vm_existence
from lyra.models._analysis import EphaistosAnalysis

EXISTING = ["arch-base", "fedora-base", "test-vm", "testuuuuu", "ubuntu-base",
            "windows-11-test", "preprod-09"]


@pytest.mark.parametrize("spoken,expected", [
    ("test-vm", "test-vm"),             # exact
    ("test vm", "test-vm"),             # espace parle
    ("Test VM", "test-vm"),             # casse
    ("test_vm", "test-vm"),             # underscore
    ("preprod 09", "preprod-09"),
    ("ubuntu", "ubuntu-base"),          # sous-chaine unique
    ("windows", "windows-11-test"),
    ("fedora base", "fedora-base"),
    ("preprod-9", "preprod-09"),        # quasi-identique unique
])
def test_resolves_spoken_forms(spoken, expected):
    assert resolve_vm_name(spoken, EXISTING) == expected


@pytest.mark.parametrize("spoken", [
    "test",        # test-vm ET testuuuuu : ambigu
    "base",        # trois VM
    "veme",        # rien de proche
    "",
    "  ",
])
def test_ambiguous_or_unknown_is_not_resolved(spoken):
    assert resolve_vm_name(spoken, EXISTING) is None


def test_exact_only_accepts_normalized_equality_but_no_fuzzy_guess():
    assert resolve_vm_name("Test VM", EXISTING, exact_only=True) == "test-vm"
    assert resolve_vm_name("ubuntu", EXISTING, exact_only=True) is None
    assert resolve_vm_name("preprod-9", EXISTING, exact_only=True) is None


def test_resolve_does_not_mutate_the_list():
    snapshot = list(EXISTING)
    resolve_vm_name("test vm", EXISTING)
    assert EXISTING == snapshot


class _Session:
    def __init__(self):
        self.turns = []

    def add_turn(self, user_input, assistant_response):
        self.turns.append((user_input, assistant_response))


def _analysis(tool, vm_name):
    return EphaistosAnalysis(tool=tool, arguments={"vm_name": vm_name}, missing_args=[],
                             confidence=0.9, reasoning="", raw_response="")


@pytest.fixture
def vms(monkeypatch):
    monkeypatch.setattr(validation, "get_existing_vm_names", lambda hestia: list(EXISTING))
    monkeypatch.setattr(validation, "get_vm_state",
                        lambda hestia, name: {"running": True, "ip": None})


def test_validate_replaces_spoken_name_by_real_one(vms):
    analysis = _analysis("vm_stop", "test vm")
    original_args = analysis.arguments
    result = validate_vm_existence(None, _Session(), analysis, "arrete la vm test vm")
    assert result is None
    assert analysis.arguments["vm_name"] == "test-vm"
    assert original_args == {"vm_name": "test vm"}  # ancien dict intact


def test_validate_still_reports_unknown_vm(vms):
    result = validate_vm_existence(None, _Session(), _analysis("vm_stop", "veme"), "q")
    assert result is not None and "n'existe pas" in result.response


def test_destructive_tool_never_guesses(vms):
    """vm_destroy : "ubuntu" ne devient pas "ubuntu-base" par approximation."""
    analysis = _analysis("vm_destroy", "ubuntu")
    result = validate_vm_existence(None, _Session(), analysis, "supprime ubuntu")
    assert result is not None and "n'existe pas" in result.response
    assert analysis.arguments["vm_name"] == "ubuntu"


def test_destructive_tool_accepts_exact_normalized_name(vms):
    analysis = _analysis("vm_destroy", "Test VM")
    assert validate_vm_existence(None, _Session(), analysis, "q") is None
    assert analysis.arguments["vm_name"] == "test-vm"
