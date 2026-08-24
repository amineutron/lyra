"""Le prompt de confirmation doit rendre les actions destructives evidentes."""
from lyra.daemon.remote_ui import build_confirm_prompt


def test_outil_dangereux_mis_en_avant():
    prompt, danger = build_confirm_prompt("fedora.vm_destroy", {"vm_name": "test-vm"})
    assert danger is True
    assert "ACTION DESTRUCTIVE" in prompt and "irreversible" in prompt
    assert "vm_name=test-vm" in prompt


def test_outil_normal_reste_simple():
    prompt, danger = build_confirm_prompt("fedora.vm_start", {"vm_name": "test-vm"})
    assert danger is False
    assert "DESTRUCTIVE" not in prompt and "vm_name=test-vm" in prompt


def test_denomination_courte_et_longue():
    assert build_confirm_prompt("vm_stop", {})[1] is True
    assert build_confirm_prompt("hue.turn_on_group", {"group_id": 81})[1] is False


def test_sensible_mais_pas_destructif():
    # clone systeme / vm_stop : confirmation exigee mais PAS "destructive"
    # (retour utilisateur 2026-08-14 : cloner ne detruit rien)
    for tool in ("fedora.vm_clone_system", "vm_stop", "vm_exec"):
        prompt, danger = build_confirm_prompt(tool, {})
        assert danger is True
        assert "ACTION SENSIBLE" in prompt and "DESTRUCTIVE" not in prompt


def test_destructifs_restent_rouges():
    for tool in ("vm_destroy", "backup_restore", "backup_clean"):
        assert "ACTION DESTRUCTIVE" in build_confirm_prompt(tool, {})[0]


def test_prefixe_serveur_reconnu_dangereux():
    # Regression 2026-08-14 : actions.py comparait "fedora.vm_stop" au set de
    # noms courts -> is_dangerous=False -> reponse vide = confirmation.
    from lyra.core.constants import is_dangerous_tool, is_destructive_tool
    assert is_dangerous_tool("fedora.vm_clone_system")
    assert is_dangerous_tool("vm_destroy")
    assert not is_dangerous_tool("fedora.vm_status")
    assert is_destructive_tool("fedora.vm_destroy")
    assert not is_destructive_tool("fedora.vm_clone_system")
