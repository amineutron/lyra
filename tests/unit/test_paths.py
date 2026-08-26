"""lyra/core/paths.py : resolution de l'emplacement des scripts systeme.

Regression audit 2026-08-26 : chemins /home/<user>/dev/fedora-setup codes en
dur dans modules/mcp.py, modules/n8n.py et main.py -> lecture de
paths.scripts / LYRA_SCRIPTS_DIR avec fallback /usr/local/lib/lyra/scripts.
"""
from pathlib import Path

import pytest

from lyra.core import paths
from modules.n8n import _build_fallback_cmd


def test_defaut_copie_systeme():
    assert paths.scripts_dir({}, {}) == Path("/usr/local/lib/lyra/scripts")


def test_config_yaml_prioritaire_sur_defaut():
    assert paths.scripts_dir({"paths": {"scripts": "/opt/lyra-scripts"}}, {}) == Path("/opt/lyra-scripts")


def test_env_prioritaire_sur_config():
    cfg = {"paths": {"scripts": "/opt/cfg"}}
    assert paths.scripts_dir(cfg, {"LYRA_SCRIPTS_DIR": "/opt/env"}) == Path("/opt/env")


@pytest.mark.parametrize("cfg", [{}, {"paths": None}, {"paths": {"scripts": ""}}, {"paths": "oops"}])
def test_config_partielle_ou_invalide_retombe_sur_defaut(cfg):
    assert paths.scripts_dir(cfg, {"LYRA_SCRIPTS_DIR": "  "}) == Path("/usr/local/lib/lyra/scripts")


def test_load_config_absente_ou_cassee(tmp_path):
    assert paths.load_config(tmp_path / "absent.yaml") == {}
    bad = tmp_path / "bad.yaml"
    bad.write_text("paths: [unclosed")
    assert paths.load_config(bad) == {}
    good = tmp_path / "config.yaml"
    good.write_text("paths:\n  scripts: /srv/s\n")
    assert paths.scripts_dir_from_config(good) == Path("/srv/s")


def test_sous_dossiers():
    base = Path("/x")
    assert paths.vm_controller_dir(base) == Path("/x/agents/vm-controller")
    assert paths.backup_manager_dir(base) == Path("/x/agents/backup-manager")
    assert paths.kvm_dir(base) == Path("/x/kvm")


def test_aucun_chemin_utilisateur_dans_le_code():
    """Le bug d'origine : un /home/<user> en dur dans le code applicatif."""
    root = paths.LYRA_ROOT
    for rel in ("main.py", "modules/n8n.py", "modules/mcp.py", "lyra/core/config.py",
                "lyra/core/paths.py", "installer/core/steps/mcps.py"):
        assert "/home/amineutron" not in (root / rel).read_text(), rel


def test_fallback_n8n_utilise_scripts_dir(monkeypatch):
    monkeypatch.setenv("LYRA_SCRIPTS_DIR", "/opt/s")
    cmd = _build_fallback_cmd("vm_clone", {"source_vm": "tpl", "new_vm_name": "vm1"})
    assert cmd == ["/opt/s/kvm/kvm-clone.sh", "tpl", "vm1", "--start"]
    cmd = _build_fallback_cmd("backup_create", {"type": "borg"})
    assert cmd == ["/opt/s/agents/backup-manager/backup-create.sh", "borg"]
    assert _build_fallback_cmd("vm_clone", {"source_vm": "a;rm", "new_vm_name": "b"}) is None
