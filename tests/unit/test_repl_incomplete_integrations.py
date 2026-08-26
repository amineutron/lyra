"""Regression : le client doit rappeler au demarrage les MCPs selectionnes
a l'install mais restes incomplets (device manquant, paquet casse...) --
voir installer/core/pipeline.py (optional=True) + steps/config.py qui
ecrivent cette liste dans config.yaml (cle incomplete_integrations)."""
from lyra.client.repl import _print_incomplete_integrations


def test_rappel_affiche_pour_chaque_integration_incomplete(capsys):
    cfg = {
        "incomplete_integrations": [
            {"id": "mcp_hue", "label": "MCP hue-mcp",
             "reason": "IP du bridge Hue manquante"},
            {"id": "mcp_pylips", "label": "MCP pylips-mcp",
             "reason": "pip install a echoue (code 1)"},
        ]
    }
    _print_incomplete_integrations(cfg)
    out = capsys.readouterr().out
    assert "hue-mcp" in out and "IP du bridge Hue manquante" in out
    assert "pylips-mcp" in out and "pip install a echoue" in out
    assert "install.sh" in out


def test_rien_affiche_si_pas_dincomplet(capsys):
    _print_incomplete_integrations({})
    assert capsys.readouterr().out == ""
