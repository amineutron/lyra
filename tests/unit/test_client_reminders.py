"""Regression : le client doit rappeler au demarrage (REPL ET one-shot)
les MCPs selectionnes a l'install mais restes incomplets (device manquant,
paquet casse...) -- voir installer/core/pipeline.py (optional=True) +
steps/config.py qui ecrivent cette liste dans config.yaml (cle
incomplete_integrations). Partage entre repl.py et __main__.py (one-shot
n'affichait pas le rappel avant : seul le REPL le montrait)."""
from lyra.client.reminders import print_incomplete_integrations


def test_rappel_affiche_pour_chaque_integration_incomplete(capsys):
    cfg = {
        "incomplete_integrations": [
            {"id": "mcp_hue", "label": "MCP hue-mcp",
             "reason": "IP du bridge Hue manquante"},
            {"id": "mcp_pylips", "label": "MCP pylips-mcp",
             "reason": "pip install a echoue (code 1)"},
        ]
    }
    print_incomplete_integrations(cfg)
    out = capsys.readouterr().out
    assert "hue-mcp" in out and "IP du bridge Hue manquante" in out
    assert "pylips-mcp" in out and "pip install a echoue" in out
    assert "install.sh" in out


def test_rien_affiche_si_pas_dincomplet(capsys):
    print_incomplete_integrations({})
    assert capsys.readouterr().out == ""
