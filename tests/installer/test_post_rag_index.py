"""Regression : une installation neuve doit construire l'index v3 (lu en production)."""
from installer.core.steps.post import rag_index_commands


def _touch(root, *names):
    (root / "scripts").mkdir(exist_ok=True)
    for n in names:
        (root / "scripts" / n).write_text("")


def test_v2_puis_v3_dans_l_ordre(tmp_path):
    _touch(tmp_path, "reindex_mcp_rag_optimized.py", "index_rag_3tier.py")
    cmds = [c for _, c in rag_index_commands(tmp_path, "py")]
    assert cmds == [["py", str(tmp_path / "scripts" / "reindex_mcp_rag_optimized.py")],
                    ["py", str(tmp_path / "scripts" / "index_rag_3tier.py"), "--clear"]]


def test_sans_script_v3_seulement_v2(tmp_path):
    _touch(tmp_path, "reindex_mcp_rag_optimized.py")
    assert len(rag_index_commands(tmp_path, "py")) == 1


def test_ancien_depot(tmp_path):
    _touch(tmp_path, "index_mcp_specs.py")
    assert [c for _, c in rag_index_commands(tmp_path, "py")] == [["py", str(tmp_path / "scripts" / "index_mcp_specs.py")]]
    assert rag_index_commands(tmp_path / "vide", "py") == []


def test_depot_reel_construit_la_v3():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    assert any("--clear" in c for _, c in rag_index_commands(root, "py"))
