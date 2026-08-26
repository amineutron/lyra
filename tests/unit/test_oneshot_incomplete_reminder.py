"""Regression : le rappel d'integrations incompletes n'etait affiche qu'en
mode REPL -- un utilisateur qui n'utilise que le one-shot (`lyra -y "..."`,
le mode documente dans CLAUDE.md pour les tests rapides) ne le voyait
jamais. _print_incomplete_integrations_reminder() est maintenant appele
aussi dans run_oneshot_via_daemon()."""
from pathlib import Path
from unittest.mock import patch

import yaml

from lyra.client.__main__ import _print_incomplete_integrations_reminder


def test_reminder_lit_config_et_affiche(tmp_path, capsys):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump({
        "incomplete_integrations": [
            {"id": "mcp_hue", "label": "MCP hue-mcp", "reason": "IP manquante"},
        ]
    }))
    with patch("lyra.client.__main__.REPO_ROOT", tmp_path):
        _print_incomplete_integrations_reminder()
    out = capsys.readouterr().out
    assert "hue-mcp" in out and "IP manquante" in out


def test_reminder_ne_plante_jamais_si_config_absent(tmp_path, capsys):
    with patch("lyra.client.__main__.REPO_ROOT", tmp_path):
        _print_incomplete_integrations_reminder()  # ne doit pas lever
    assert capsys.readouterr().out == ""
