"""Regression 2026-08-14 : vm_clone_system lance SANS sudo par le wrapper
-> echec immediat (check_root) et session tracking bloquee en "running 0%".
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from async_mcp_wrapper import finalize_cmd, build_args_vm_clone_system


def test_clone_system_sudo_et_tracking():
    cmd = finalize_cmd("vm_clone_system", ["/x/kvm-clone-system.sh", "-n", "vm1"],
                       tracking_id="db3f6e88")
    assert cmd[:2] == ["sudo", "-n"]
    assert cmd[-2:] == ["--tracking-id", "db3f6e88"]


def test_clone_system_sans_tracking():
    cmd = finalize_cmd("vm_clone_system", ["/x/s.sh"])
    assert cmd == ["sudo", "-n", "/x/s.sh"]


def test_backups_sudo_sans_flag_tracking():
    for tool in ("backup_create", "backup_restore"):
        cmd = finalize_cmd(tool, ["/x/b.sh"], tracking_id="abcd1234")
        assert cmd[:2] == ["sudo", "-n"]
        assert "--tracking-id" not in cmd


def test_outils_user_non_decores():
    for tool in ("vm_clone", "vm_export", "vm_import"):
        assert finalize_cmd(tool, ["/x/t.sh"], tracking_id="abcd1234") == ["/x/t.sh"]


def test_builder_clone_system_light_par_defaut():
    # le mode leger est le defaut : pas de --full sans demande explicite
    cmd = build_args_vm_clone_system({"name": "test-vm01"})
    assert "--full" not in cmd
    assert "-n" in cmd and "test-vm01" in cmd
    # 80G par defaut : 60G saturait (ENOSPC grub2-install) — qcow2 reste sparse
    assert "80G" in cmd
