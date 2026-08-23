"""Tests detection de distribution (logique pure)."""
import pytest

from installer.core.osdetect import parse_os_release

FEDORA = 'NAME="Fedora Linux"\nID=fedora\nPRETTY_NAME="Fedora Linux 43"\n'
UBUNTU = 'NAME="Ubuntu"\nID=ubuntu\nID_LIKE=debian\nPRETTY_NAME="Ubuntu 24.04"\n'
ARCH = 'NAME="Arch Linux"\nID=arch\nPRETTY_NAME="Arch Linux"\n'
MINT = 'ID=linuxmint\nID_LIKE="ubuntu debian"\nPRETTY_NAME="Linux Mint 22"\n'
INCONNU = 'ID=haiku\nPRETTY_NAME="Haiku"\n'


@pytest.mark.parametrize("text,expected_family,supported", [
    (FEDORA, "fedora", True),
    (UBUNTU, "debian", True),
    (ARCH, "arch", True),
    (MINT, "debian", True),
    (INCONNU, "unknown", False),
    ("", "unknown", False),
])
def test_familles(text, expected_family, supported):
    d = parse_os_release(text)
    assert d.family == expected_family
    assert d.supported is supported


def test_nodejs_present_partout():
    # Regression : l'ancien installeur .py omettait nodejs/npm (requis
    # par fedora-agents). Chaque famille doit les fournir.
    for text in (FEDORA, UBUNTU, ARCH):
        d = parse_os_release(text)
        assert "npm" in d.packages, d.family
        assert any(p.startswith("nodejs") for p in d.packages), d.family


def test_install_cmd_par_famille():
    assert parse_os_release(FEDORA).install_cmd[:2] == ["sudo", "dnf"]
    assert parse_os_release(UBUNTU).install_cmd[:2] == ["sudo", "apt-get"]
    assert parse_os_release(ARCH).install_cmd[:2] == ["sudo", "pacman"]
    assert parse_os_release(INCONNU).install_cmd == []
