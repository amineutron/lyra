"""Tests de validation de format des arguments du wrapper async.

Regression pour l'audit securite 2026-07-29 : les valeurs extraites par
LLM/regex depuis du texte libre doivent etre validees (whitelist) avant
d'etre passees en argv aux scripts bash de fedora-setup.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from async_mcp_wrapper import (  # noqa: E402
    build_args_backup_create,
    build_args_backup_restore,
    build_args_vm_clone,
    build_args_vm_export,
    build_args_vm_import,
    validate_safe_name,
    validate_safe_path,
    validate_safe_text,
)


# ---- validate_safe_name ----

@pytest.mark.parametrize("value", [
    "preprod-01", "test_clone", "neutron.v2", "60G", "a", "A" * 64,
])
def test_safe_name_accepts_valid(value):
    assert validate_safe_name(value, "vm_name") == value


@pytest.mark.parametrize("value", [
    "$(rm -rf ~)", "vm;reboot", "vm name", "vm|cat", "`id`", "vm\nls",
    "-rf", "--force-hidden", "", None, 42, "A" * 65, "../etc/passwd",
])
def test_safe_name_rejects_invalid(value):
    with pytest.raises(ValueError):
        validate_safe_name(value, "vm_name")


# ---- validate_safe_path ----

@pytest.mark.parametrize("value", [
    "/mnt/backup/vm.tar.gz", "~/exports/vm-01.qcow2", "relative/path.img",
])
def test_safe_path_accepts_valid(value):
    assert validate_safe_path(value, "archive_path") == value


@pytest.mark.parametrize("value", [
    "/mnt/x; rm -rf /", "/path with space", "$(pwd)/x", "-o/evil", "", None,
])
def test_safe_path_rejects_invalid(value):
    with pytest.raises(ValueError):
        validate_safe_path(value, "archive_path")


# ---- validate_safe_text ----

def test_safe_text_accepts_plain_comment():
    assert validate_safe_text("backup avant migration v2", "comment")


@pytest.mark.parametrize("value", [
    "avant $(reboot)", "x`id`y", "a;b", 'quote"quote', "back\\slash",
])
def test_safe_text_rejects_shell_metachars(value):
    with pytest.raises(ValueError):
        validate_safe_text(value, "comment")


# ---- builders : la validation est bien branchee ----

def test_vm_clone_builder_valid():
    cmd = build_args_vm_clone({"source_vm": "preprod-09", "new_vm_name": "test-clone"})
    assert cmd[-2:] == ["preprod-09", "test-clone"]


@pytest.mark.parametrize("builder,args", [
    (build_args_vm_clone, {"source_vm": "$(reboot)", "new_vm_name": "x"}),
    (build_args_vm_export, {"vm_name": "vm;ls"}),
    (build_args_vm_export, {"vm_name": "ok", "output_path": "/tmp/x; rm -rf /"}),
    (build_args_vm_import, {"archive_path": "/mnt/a.tar.gz", "new_name": "-rf"}),
    (build_args_backup_create, {"type": "full", "comment": "x`id`"}),
    (build_args_backup_restore, {"type": "full", "identifier": "a b"}),
])
def test_builders_reject_malicious_args(builder, args):
    with pytest.raises(ValueError):
        builder(args)
