"""Tests de la substitution du template lyra-daemon.service."""
from pathlib import Path

from installer.core.steps.systemd import render_service

TEMPLATE = Path("/home/amineutron/dev/lyra/install/lyra-daemon.service").read_text()


def test_chemins_substitues():
    out = render_service(TEMPLATE, "/opt/lyra", "/home/bob")
    assert "/home/amineutron/dev/lyra" not in out
    assert "WorkingDirectory=/opt/lyra" in out
    assert "ExecStart=/opt/lyra/.venv/bin/python -m lyra.daemon" in out


def test_path_venv_en_tete():
    out = render_service(TEMPLATE, "/opt/lyra", "/home/bob")
    path_line = next(l for l in out.splitlines()
                     if l.startswith("Environment=PATH="))
    assert path_line.split("=", 2)[2].split(":")[0] == "/opt/lyra/.venv/bin"
    # le chemin android-sdk propre a la machine de dev ne doit pas fuiter
    assert "nvme-storage" not in path_line


def test_pas_de_nonewprivileges():
    out = render_service(TEMPLATE, "/opt/lyra", "/home/bob")
    assert "NoNewPrivileges=true" not in out
