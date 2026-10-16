"""Durcissement du demon et des taches de fond (rapport de modele de menaces, 2026-10-16)."""
import importlib
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def test_wrapper_utilise_la_copie_systeme_des_scripts(monkeypatch, tmp_path):
    """Regression : le wrapper visait ~/dev/fedora-setup/scripts, sans regle sudoers (sudo -n
    echouait) et inscriptible par l'utilisateur ; il suit maintenant lyra.core.paths."""
    monkeypatch.setenv("LYRA_SCRIPTS_DIR", str(tmp_path))
    monkeypatch.syspath_prepend(str(SCRIPTS))
    sys.modules.pop("async_mcp_wrapper", None)
    wrapper = importlib.import_module("async_mcp_wrapper")
    assert wrapper.FEDORA_BASE == tmp_path
    assert wrapper.build_args_vm_clone_system({"name": "vm1"})[0].startswith(str(tmp_path))
    assert "fedora-setup" not in str(wrapper.BACKUP)


def test_chemin_par_defaut_est_la_copie_root(monkeypatch):
    monkeypatch.delenv("LYRA_SCRIPTS_DIR", raising=False)
    from lyra.core.paths import scripts_dir
    assert scripts_dir({}, env={}) == Path("/usr/local/lib/lyra/scripts")


def test_webhook_hors_de_la_ligne_de_commande():
    """L'adresse du webhook ne doit pas apparaitre dans argv (lisible par tous via /proc)."""
    from lyra.hestia.background_tasks import BackgroundTaskManager
    m = BackgroundTaskManager.__new__(BackgroundTaskManager)
    cmd = m._build_command("task_x", "fedora.vm_clone", {"source_vm": "a"}, "https://discord.test/api/webhooks/secret")
    assert not any("discord.test" in c for c in cmd)
    assert "--webhook" not in cmd
