"""Tests unitaires pour lyra/rules/vm.py."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from lyra.rules.vm import detect


def tool(q):
    r = detect(q)
    return r.tool if r else None


def args(q):
    r = detect(q)
    return r.arguments if r else {}


# ------------------------------------------------------------------ #
# vm_clone_system (avant vm_clone)                                    #
# ------------------------------------------------------------------ #

class TestVmCloneSystem:
    def test_clone_systeme(self):
        assert tool("clone systeme preprod-01 en clone-system") == "fedora.vm_clone_system"

    def test_clone_system_anglais(self):
        assert tool("clone system preprod-01 en backup-system") == "fedora.vm_clone_system"

    def test_args_extracted(self):
        a = args("clone systeme preprod-01 en neutron-clone")
        assert a.get("source_vm") == "preprod-01"
        assert a.get("new_vm_name") == "neutron-clone"


# ------------------------------------------------------------------ #
# vm_clone                                                            #
# ------------------------------------------------------------------ #

class TestVmClone:
    def test_clone_source_en_dest(self):
        assert tool("clone preprod-01 en test-clone") == "fedora.vm_clone"

    def test_duplique(self):
        assert tool("duplique fedora-base en fedora-test") == "fedora.vm_clone"

    def test_args_extracted(self):
        a = args("clone preprod-01 en test-clone")
        assert a.get("source_vm") == "preprod-01"
        assert a.get("new_vm_name") == "test-clone"

    def test_copie_de_vm(self):
        assert tool("fais une copie de fedora-base") == "fedora.vm_clone"

    def test_copie_source_extracted(self):
        a = args("fais une copie de fedora-base")
        assert a.get("source_vm") == "fedora-base"

    def test_not_system(self):
        # Sans "system/systeme" -> vm_clone, pas vm_clone_system
        assert tool("clone preprod-01 en test-01") == "fedora.vm_clone"


# ------------------------------------------------------------------ #
# vm_copy                                                             #
# ------------------------------------------------------------------ #

class TestVmCopy:
    def test_copie_fichier_vers_vm(self):
        assert tool("copie fichier.txt vers preprod-01") == "fedora.vm_copy"

    def test_transfere_vers_vm(self):
        assert tool("transfere script.sh sur fedora-base") == "fedora.vm_copy"

    def test_args_extracted(self):
        a = args("copie script.sh vers preprod-01")
        assert a.get("vm_name") == "preprod-01"
        assert "script.sh" in a.get("source", "")


# ------------------------------------------------------------------ #
# vm_verify                                                           #
# ------------------------------------------------------------------ #

class TestVmVerify:
    def test_verifie_vm(self):
        assert tool("verifie preprod-01") == "fedora.vm_verify"

    def test_vm_extracted(self):
        a = args("verifie preprod-01")
        assert a.get("vm_name") == "preprod-01"

    def test_check_vm(self):
        assert tool("check neutron-template") == "fedora.vm_verify"

    def test_verif_vm(self):
        assert tool("verif fedora-base") == "fedora.vm_verify"

    def test_quick_flag(self):
        # La regle matche \brapide\b ou \bvite\b (pas "rapidement" avec \b)
        a = args("verifie preprod-01 vite")
        assert a.get("quick") is True

    def test_no_backup_collision(self):
        # "verifie le backup" -> backup_verify (géré par backup.py, avant vm dans registry)
        # Ici on teste que vm.py seul ne le capture pas quand "backup" est présent
        assert tool("verifie backup de preprod-01") is None


# ------------------------------------------------------------------ #
# vm_start                                                            #
# ------------------------------------------------------------------ #

class TestVmStart:
    def test_demarre_vm(self):
        assert tool("demarre preprod-01") == "fedora.vm_start"

    def test_vm_name_extracted(self):
        a = args("demarre preprod-01")
        assert a.get("vm_name") == "preprod-01"

    def test_lance_vm(self):
        assert tool("lance fedora-base") == "fedora.vm_start"

    def test_allume_vm(self):
        assert tool("allume neutron-template") == "fedora.vm_start"

    def test_no_tv_collision(self):
        # Contexte TV -> pas vm_start
        assert tool("lance netflix sur la tv") is None

    def test_no_hue_collision(self):
        assert tool("allume les lumieres") is None


# ------------------------------------------------------------------ #
# vm_stop                                                             #
# ------------------------------------------------------------------ #

class TestVmStop:
    def test_arrete_vm(self):
        assert tool("arrete preprod-01") == "fedora.vm_stop"

    def test_vm_name_extracted(self):
        a = args("arrete preprod-01")
        assert a.get("vm_name") == "preprod-01"

    def test_stoppe_vm(self):
        assert tool("stoppe fedora-base") == "fedora.vm_stop"

    def test_force_flag(self):
        a = args("arrete de force preprod-01")
        assert a.get("force") is True

    def test_no_denon_collision(self):
        # Contexte denon -> pas vm_stop
        assert tool("arrete le denon") is None


# ------------------------------------------------------------------ #
# vm_destroy                                                          #
# ------------------------------------------------------------------ #

class TestVmDestroy:
    def test_supprime_vm(self):
        assert tool("supprime sandbox-01") == "fedora.vm_destroy"

    def test_vm_name_extracted(self):
        a = args("supprime sandbox-01")
        assert a.get("vm_name") == "sandbox-01"

    def test_detruit_vm(self):
        assert tool("detruit fedora-test") == "fedora.vm_destroy"

    def test_efface_vm(self):
        assert tool("efface sandbox-test") == "fedora.vm_destroy"

    def test_force_flag(self):
        a = args("supprime de force sandbox-01")
        assert a.get("force") is True


# ------------------------------------------------------------------ #
# vm_exec                                                             #
# ------------------------------------------------------------------ #

class TestVmExec:
    def test_execute_cmd_sur_vm(self):
        assert tool("execute ls sur preprod-01") == "fedora.vm_exec"

    def test_args_extracted(self):
        a = args("execute ls sur preprod-01")
        assert a.get("vm_name") == "preprod-01"
        assert a.get("command") == "ls"

    def test_exec_commande(self):
        assert tool("exec df -h sur fedora-base") == "fedora.vm_exec"


# ------------------------------------------------------------------ #
# vm_snapshot                                                         #
# ------------------------------------------------------------------ #

class TestVmSnapshot:
    def test_snapshot_vm(self):
        assert tool("snapshot preprod-01") == "fedora.vm_snapshot"

    def test_vm_name_extracted(self):
        a = args("snapshot preprod-01")
        assert a.get("vm_name") == "preprod-01"

    def test_cree_snapshot(self):
        assert tool("cree un snapshot de fedora-base") == "fedora.vm_snapshot"

    def test_live_flag(self):
        a = args("snapshot live preprod-01")
        assert a.get("live") is True


# ------------------------------------------------------------------ #
# vm_status                                                           #
# ------------------------------------------------------------------ #

class TestVmStatus:
    def test_status_vm(self):
        assert tool("status de preprod-01") == "fedora.vm_status"

    def test_vm_name_extracted(self):
        a = args("status de preprod-01")
        assert a.get("vm_name") == "preprod-01"

    def test_liste_mes_vms(self):
        assert tool("liste mes vms") == "fedora.vm_status"

    def test_liste_vms_no_name(self):
        a = args("liste mes vms")
        assert a.get("vm_name") is None

    def test_affiche_machines(self):
        assert tool("affiche les machines virtuelles") == "fedora.vm_status"

    def test_status_detaille(self):
        a = args("status detaille de preprod-01")
        assert a.get("detailed") is True


# ------------------------------------------------------------------ #
# vm_export                                                           #
# ------------------------------------------------------------------ #

class TestVmExport:
    def test_exporte_vm(self):
        assert tool("exporte preprod-01") == "fedora.vm_export"

    def test_vm_name_extracted(self):
        a = args("exporte preprod-01")
        assert a.get("vm_name") == "preprod-01"

    def test_mode_exam(self):
        a = args("exporte preprod-01 en mode exam")
        assert a.get("mode") == "exam"

    def test_mode_classic_default(self):
        a = args("exporte fedora-base")
        assert a.get("mode") == "classic"

    def test_mode_custom(self):
        a = args("exporte preprod-01 en mode custom")
        assert a.get("mode") == "custom"


# ------------------------------------------------------------------ #
# vm_import                                                           #
# ------------------------------------------------------------------ #

class TestVmImport:
    def test_importe_archive(self):
        assert tool("importe /tmp/archive.tar.gz") == "fedora.vm_import"

    def test_archive_extracted(self):
        a = args("importe /tmp/archive.tar.gz")
        assert a.get("archive_path") == "/tmp/archive.tar.gz"

    def test_avec_nouveau_nom(self):
        a = args("importe /tmp/export.tar.gz sous le nom test-vm")
        assert a.get("new_name") == "test-vm"


# ------------------------------------------------------------------ #
# Pas de match                                                        #
# ------------------------------------------------------------------ #

class TestNoMatch:
    def test_tv_query(self):
        assert tool("allume la tv") is None

    def test_hue_query(self):
        assert tool("allume les lumieres") is None

    def test_empty(self):
        assert tool("") is None
