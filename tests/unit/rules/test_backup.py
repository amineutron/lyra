"""Tests unitaires pour lyra/rules/backup.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from lyra.rules.backup import detect


def tool(q):
    r = detect(q)
    return r.tool if r else None


def args(q):
    r = detect(q)
    return r.arguments if r else {}


# ------------------------------------------------------------------ #
# backup_status                                                        #
# ------------------------------------------------------------------ #

class TestBackupStatus:
    def test_status_backup(self):
        assert tool("status backup") == "fedora.backup_status"

    def test_etat_sauvegardes(self):
        assert tool("etat des sauvegardes") == "fedora.backup_status"

    def test_dashboard_backup(self):
        assert tool("affiche le dashboard backup") == "fedora.backup_status"

    def test_watch_not_injected(self):
        r = detect("status backup")
        assert r is not None
        assert r.arguments.get("watch") is None


# ------------------------------------------------------------------ #
# backup_list                                                          #
# ------------------------------------------------------------------ #

class TestBackupList:
    def test_liste_backups(self):
        assert tool("liste les backups") == "fedora.backup_list"

    def test_affiche_sauvegardes(self):
        assert tool("affiche mes sauvegardes") == "fedora.backup_list"

    def test_montre_backups(self):
        assert tool("montre les backups") == "fedora.backup_list"

    def test_donne_moi_sauvegardes(self):
        assert tool("donne moi les sauvegardes") == "fedora.backup_list"


# ------------------------------------------------------------------ #
# backup_verify                                                        #
# ------------------------------------------------------------------ #

class TestBackupVerify:
    def test_verifie_backup(self):
        assert tool("verifie le backup") == "fedora.backup_verify"

    def test_verifie_backup_vm(self):
        assert tool("verifie backup de preprod-01") == "fedora.backup_verify"

    def test_vm_extracted(self):
        a = args("verifie backup de neutron-template")
        assert a.get("vm_name") == "neutron-template"

    def test_teste_sauvegarde(self):
        assert tool("teste la sauvegarde") == "fedora.backup_verify"

    def test_controle_backup(self):
        assert tool("controle le backup") == "fedora.backup_verify"

    def test_no_create_collision(self):
        # "cree et teste" -> backup_create (has "cree" keyword)
        assert tool("cree un nouveau backup et teste le") == "fedora.backup_create"


# ------------------------------------------------------------------ #
# backup_create                                                        #
# ------------------------------------------------------------------ #

class TestBackupCreate:
    def test_cree_backup(self):
        assert tool("cree un backup") == "fedora.backup_create"

    def test_fais_sauvegarde(self):
        assert tool("fais une sauvegarde") == "fedora.backup_create"

    def test_lance_backup(self):
        assert tool("lance un backup") == "fedora.backup_create"

    def test_vm_extracted(self):
        a = args("cree un backup de neutron-template")
        assert a.get("vm_name") == "neutron-template"

    def test_genere_backup(self):
        assert tool("genere un backup") == "fedora.backup_create"


# ------------------------------------------------------------------ #
# backup_restore                                                       #
# ------------------------------------------------------------------ #

class TestBackupRestore:
    def test_restaure_backup(self):
        assert tool("restaure le backup") == "fedora.backup_restore"

    def test_restore_anglais(self):
        assert tool("restore le backup") == "fedora.backup_restore"

    def test_recupere_sauvegarde(self):
        assert tool("recupere la sauvegarde") == "fedora.backup_restore"

    def test_identifier_extracted(self):
        a = args("restaure backup de preprod-01")
        assert a.get("identifier") == "preprod-01"


# ------------------------------------------------------------------ #
# backup_clean                                                         #
# ------------------------------------------------------------------ #

class TestBackupClean:
    def test_nettoie_backups(self):
        assert tool("nettoie les backups") == "fedora.backup_clean"

    def test_purge_sauvegardes(self):
        assert tool("purge les sauvegardes") == "fedora.backup_clean"

    def test_supprime_anciens_backups(self):
        assert tool("supprime les anciens backups") == "fedora.backup_clean"

    def test_efface_sauvegardes(self):
        assert tool("efface les sauvegardes") == "fedora.backup_clean"


# ------------------------------------------------------------------ #
# Pas de match sans mot-cle backup/sauvegarde                         #
# ------------------------------------------------------------------ #

class TestNoMatch:
    def test_random_query(self):
        assert tool("demarre preprod-01") is None

    def test_vm_query(self):
        assert tool("status de mes vms") is None

    def test_empty(self):
        assert tool("") is None


class TestPhrasesInedites:
    """Regression lyra#22 : "fais le menage dans les vieilles sauvegardes" tombait sur backup_create."""

    def test_faire_le_menage_est_un_nettoyage(self):
        r = detect("fais le menage dans les vieilles sauvegardes")
        assert r is not None and r.tool == "fedora.backup_clean"

    def test_virer_les_anciennes(self):
        r = detect("vire les anciennes sauvegardes")
        assert r is not None and r.tool == "fedora.backup_clean"

    def test_creer_reste_une_creation(self):
        r = detect("fais un backup de preprod-01")
        assert r is not None and r.tool == "fedora.backup_create"


class TestLePoint:
    """Regression lyra#23 : « fais-moi le point sur les sauvegardes » est un status, pas une creation."""

    def test_le_point_est_un_status(self):
        for q in ("fais-moi le point sur les sauvegardes", "ou en sont les sauvegardes", "le point sur les backups"):
            r = detect(q)
            assert r is not None and r.tool == "fedora.backup_status", q
