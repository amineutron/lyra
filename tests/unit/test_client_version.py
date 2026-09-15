"""Tests du drapeau --version du client CLI (issue #15)."""

from __future__ import annotations

import importlib.metadata

import pytest

from lyra.client import __main__ as client_main


def test_version_flag_prints_installed_version(monkeypatch, capsys):
    monkeypatch.setattr(importlib.metadata, "version", lambda name: "9.8.7")
    monkeypatch.setattr("sys.argv", ["lyra", "--version"])

    with pytest.raises(SystemExit) as exc:
        client_main.main()

    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == "lyra-assistant 9.8.7"


def test_version_falls_back_to_pyproject_when_not_installed(monkeypatch):
    def _missing(name):
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", _missing)

    version = client_main._package_version()

    assert version.endswith("(sources)")
    assert version.split()[0][0].isdigit()


def test_version_fallback_when_pyproject_unreadable(monkeypatch, tmp_path):
    def _missing(name):
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", _missing)
    monkeypatch.setattr(client_main, "REPO_ROOT", tmp_path)

    assert client_main._package_version() == "unknown (sources)"
