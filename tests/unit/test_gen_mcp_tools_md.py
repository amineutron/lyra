"""Le generateur de MCP_TOOLS.md rend chaque outil avec sa colonne confirmation."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from gen_mcp_tools_md import arguments, confirmation, rendre  # noqa: E402


def test_confirmation_vient_des_constantes():
    assert confirmation("fedora.vm_destroy").startswith("DESTRUCTIF")
    assert confirmation("fedora.vm_exec").startswith("SENSIBLE")
    assert confirmation("denon.volume_up").startswith("sans confirmation")
    assert confirmation("hue.create_group") == "confirmation [O/n]"


def test_arguments_avec_requis_et_enum():
    schema = {"properties": {"mode": {"type": "string", "enum": ["a", "b"]}, "n": {"type": "integer"}},
              "required": ["mode"]}
    assert arguments(schema) == "`mode` (string: a/b), `n` (integer, opt)"
    assert arguments({}) == "-"


def test_rendu_par_serveur():
    md = rendre([{"name": "tv.power_on", "description": "Allume | la TV", "parameters": {}, "_server": "tv"},
                 {"name": "fedora.vm_destroy", "description": "Supprime", "parameters": {}, "_server": "fedora"}])
    assert "## FEDORA" in md and "## TV" in md and md.index("## FEDORA") < md.index("## TV")
    assert "| `tv.power_on` | Allume / la TV | - | sans confirmation en mode performance (-p) |" in md
    assert "DESTRUCTIF" in md
