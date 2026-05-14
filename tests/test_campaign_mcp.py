#!/usr/bin/env python3
"""
Campagne de tests MCP complete - Lyra RAG v2
=============================================
Teste la detection outil + extraction arguments via _rule_based_detect.
Aucune execution de scripts reels.

Score:
  PASS    : outil correct + tous les args attendus presents
  PARTIAL : outil correct + args obligatoires OK + args optionnels manquants
  FAIL    : mauvais outil ou arg obligatoire manquant
  RULE_MISS: aucune regle ne matche (ira vers EPHAISTOS en production)

Usage:
  python3 tests/test_campaign_mcp.py
"""

import sys
import unicodedata
import re
from pathlib import Path

# Ajouter le repertoire racine au path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lyra.core.pipeline import Pipeline

# ============================================================
# Format des cas de test
# (categorie, description, query, expected_tool,
#  mandatory_args, optional_args)
#
# mandatory_args : dict - DOIT etre present (FAIL si absent)
# optional_args  : dict - mentionne dans la requete mais
#                         peut ne pas etre extrait par les regles
#                         (PARTIAL si absent, pas FAIL)
# ============================================================

TESTS = [

    # ================================================================
    # FEDORA - vm_start
    # ================================================================
    ("FEDORA/vm_start", "demarre basique",
     "demarre preprod-01",
     "fedora.vm_start", {"vm_name": "preprod-01"}, {}),

    ("FEDORA/vm_start", "lance avec nom",
     "lance la vm test-server",
     "fedora.vm_start", {"vm_name": "test-server"}, {}),

    ("FEDORA/vm_start", "boot",
     "booter sandbox-02",
     "fedora.vm_start", {"vm_name": "sandbox-02"}, {}),

    ("FEDORA/vm_start", "+ wait_ssh",
     "demarre preprod-01 et attends le ssh",
     "fedora.vm_start", {"vm_name": "preprod-01"}, {"wait_ssh": True}),

    ("FEDORA/vm_start", "+ wait_ip",
     "demarre preprod-01 et attends son ip",
     "fedora.vm_start", {"vm_name": "preprod-01"}, {"wait_ip": True}),

    ("FEDORA/vm_start", "alias start",
     "start preprod-09",
     "fedora.vm_start", {"vm_name": "preprod-09"}, {}),

    # ================================================================
    # FEDORA - vm_stop
    # ================================================================
    ("FEDORA/vm_stop", "arrete basique",
     "arrete preprod-01",
     "fedora.vm_stop", {"vm_name": "preprod-01"}, {}),

    ("FEDORA/vm_stop", "stoppe",
     "stoppe sandbox-02",
     "fedora.vm_stop", {"vm_name": "sandbox-02"}, {}),

    ("FEDORA/vm_stop", "+ force",
     "arrete de force preprod-01",
     "fedora.vm_stop", {"vm_name": "preprod-01"}, {"force": True}),

    ("FEDORA/vm_stop", "stop alias",
     "stop neutron-clone",
     "fedora.vm_stop", {"vm_name": "neutron-clone"}, {}),

    # ================================================================
    # FEDORA - vm_destroy
    # ================================================================
    ("FEDORA/vm_destroy", "supprime basique",
     "supprime la vm sandbox-01",
     "fedora.vm_destroy", {"vm_name": "sandbox-01"}, {}),

    ("FEDORA/vm_destroy", "detruit",
     "detruis test-vm",
     "fedora.vm_destroy", {"vm_name": "test-vm"}, {}),

    ("FEDORA/vm_destroy", "efface",
     "efface la machine sandbox-02",
     "fedora.vm_destroy", {"vm_name": "sandbox-02"}, {}),

    ("FEDORA/vm_destroy", "+ force",
     "supprime de force sandbox-01",
     "fedora.vm_destroy", {"vm_name": "sandbox-01"}, {"force": True}),

    ("FEDORA/vm_destroy", "+ keep_storage",
     "supprime sandbox-01 mais garde le disque",
     "fedora.vm_destroy", {"vm_name": "sandbox-01"}, {"keep_storage": True}),

    # ================================================================
    # FEDORA - vm_status
    # ================================================================
    ("FEDORA/vm_status", "status specifique",
     "status de preprod-01",
     "fedora.vm_status", {"vm_name": "preprod-01"}, {}),

    ("FEDORA/vm_status", "etat VM",
     "etat de la vm test-server",
     "fedora.vm_status", {"vm_name": "test-server"}, {}),

    ("FEDORA/vm_status", "liste toutes VMs",
     "liste mes vms",
     "fedora.vm_status", {}, {}),

    ("FEDORA/vm_status", "affiche les machines",
     "affiche toutes les machines virtuelles",
     "fedora.vm_status", {}, {}),

    ("FEDORA/vm_status", "quelles sont mes VMs",
     "quelles sont mes vms",
     "fedora.vm_status", {}, {}),

    ("FEDORA/vm_status", "+ detailed",
     "status detaille de preprod-01",
     "fedora.vm_status", {"vm_name": "preprod-01"}, {"detailed": True}),

    ("FEDORA/vm_status", "donne moi les serveurs",
     "donne moi la liste des serveurs",
     "fedora.vm_status", {}, {}),

    # ================================================================
    # FEDORA - vm_exec
    # ================================================================
    ("FEDORA/vm_exec", "execute commande",
     "execute ls -la sur preprod-01",
     "fedora.vm_exec", {"vm_name": "preprod-01", "command": "ls -la"}, {}),

    ("FEDORA/vm_exec", "execute uptime",
     "execute uptime sur sandbox-02",
     "fedora.vm_exec", {"vm_name": "sandbox-02", "command": "uptime"}, {}),

    ("FEDORA/vm_exec", "lance commande",
     "lance la commande df -h sur test-server",
     "fedora.vm_exec", {"vm_name": "test-server", "command": "df -h"}, {}),

    ("FEDORA/vm_exec", "+ sudo",
     "execute systemctl restart nginx sur preprod-01 en sudo",
     "fedora.vm_exec", {"vm_name": "preprod-01"}, {"sudo": True}),

    ("FEDORA/vm_exec", "+ user",
     "execute whoami dans preprod-01",
     "fedora.vm_exec", {"vm_name": "preprod-01", "command": "whoami"}, {}),

    # ================================================================
    # FEDORA - vm_copy
    # ================================================================
    ("FEDORA/vm_copy", "copie fichier vers VM",
     "copie /tmp/config.yaml vers preprod-01",
     "fedora.vm_copy", {"vm_name": "preprod-01", "source": "/tmp/config.yaml"}, {}),

    ("FEDORA/vm_copy", "transfere vers VM",
     "transfere /home/user/script.sh sur sandbox-02",
     "fedora.vm_copy", {"vm_name": "sandbox-02", "source": "/home/user/script.sh"}, {}),

    ("FEDORA/vm_copy", "envoie fichier",
     "envoie /etc/nginx.conf dans test-server",
     "fedora.vm_copy", {"vm_name": "test-server", "source": "/etc/nginx.conf"}, {}),

    ("FEDORA/vm_copy", "+ recursive",
     "copie /home/user/projet vers preprod-01 en recursif",
     "fedora.vm_copy", {"vm_name": "preprod-01"}, {"recursive": True}),

    # ================================================================
    # FEDORA - vm_snapshot
    # ================================================================
    ("FEDORA/vm_snapshot", "cree snapshot",
     "cree un snapshot de preprod-01",
     "fedora.vm_snapshot", {"vm_name": "preprod-01"}, {}),

    ("FEDORA/vm_snapshot", "snapshot direct",
     "snapshot sandbox-02",
     "fedora.vm_snapshot", {"vm_name": "sandbox-02"}, {}),

    ("FEDORA/vm_snapshot", "instantane",
     "instantane de test-server",
     "fedora.vm_snapshot", {"vm_name": "test-server"}, {}),

    ("FEDORA/vm_snapshot", "capture",
     "capture preprod-01",
     "fedora.vm_snapshot", {"vm_name": "preprod-01"}, {}),

    ("FEDORA/vm_snapshot", "+ live",
     "cree un snapshot live de preprod-01",
     "fedora.vm_snapshot", {"vm_name": "preprod-01"}, {"live": True}),

    # ================================================================
    # FEDORA - vm_clone
    # ================================================================
    ("FEDORA/vm_clone", "clone basique",
     "clone preprod-01 en test-clone",
     "fedora.vm_clone", {"source_vm": "preprod-01", "new_vm_name": "test-clone"}, {}),

    ("FEDORA/vm_clone", "duplique",
     "duplique sandbox-02 en sandbox-03",
     "fedora.vm_clone", {"source_vm": "sandbox-02", "new_vm_name": "sandbox-03"}, {}),

    ("FEDORA/vm_clone", "+ COW/linked",
     "clone preprod-01 en test-cow en cow",
     "fedora.vm_clone", {"source_vm": "preprod-01", "new_vm_name": "test-cow"}, {"linked": True}),

    ("FEDORA/vm_clone", "+ start apres",
     "clone preprod-01 en test-clone et demarre",
     "fedora.vm_clone", {"source_vm": "preprod-01", "new_vm_name": "test-clone"}, {"start": True}),

    # ================================================================
    # FEDORA - vm_clone_system
    # ================================================================
    ("FEDORA/vm_clone_system", "clone systeme basique",
     "clone systeme neutron en neutron-clone",
     "fedora.vm_clone_system", {}, {}),

    ("FEDORA/vm_clone_system", "duplique systeme",
     "duplique le systeme neutron en backup-system",
     "fedora.vm_clone_system", {}, {}),

    ("FEDORA/vm_clone_system", "+ dry_run",
     "clone systeme neutron en test en mode dry-run",
     "fedora.vm_clone_system", {}, {"dry_run": True}),

    # ================================================================
    # FEDORA - vm_verify
    # ================================================================
    ("FEDORA/vm_verify", "verifie VM specifique",
     "verifie neutron-clone",
     "fedora.vm_verify", {"vm_name": "neutron-clone"}, {}),

    ("FEDORA/vm_verify", "verifie la VM",
     "verifie la vm preprod-01",
     "fedora.vm_verify", {"vm_name": "preprod-01"}, {}),

    ("FEDORA/vm_verify", "verif alias",
     "verif sandbox-02",
     "fedora.vm_verify", {"vm_name": "sandbox-02"}, {}),

    ("FEDORA/vm_verify", "+ quick",
     "verifie rapidement neutron-clone",
     "fedora.vm_verify", {"vm_name": "neutron-clone"}, {"quick": True}),

    ("FEDORA/vm_verify", "+ verbose",
     "verifie neutron-clone en detail",
     "fedora.vm_verify", {"vm_name": "neutron-clone"}, {"verbose": True}),

    ("FEDORA/vm_verify", "+ compare_packages",
     "verifie neutron-clone avec comparaison des paquets",
     "fedora.vm_verify", {"vm_name": "neutron-clone"}, {"compare_packages": True}),

    # ================================================================
    # FEDORA - vm_export
    # ================================================================
    ("FEDORA/vm_export", "export classic defaut",
     "exporte preprod-01",
     "fedora.vm_export", {"vm_name": "preprod-01", "mode": "classic"}, {}),

    ("FEDORA/vm_export", "export mode exam",
     "exporte preprod-01 en mode exam",
     "fedora.vm_export", {"vm_name": "preprod-01", "mode": "exam"}, {}),

    ("FEDORA/vm_export", "export mode examen",
     "exporte system-clone-final mode examen",
     "fedora.vm_export", {"vm_name": "system-clone-final", "mode": "exam"}, {}),

    ("FEDORA/vm_export", "export mode custom",
     "exporte preprod-01 en mode custom",
     "fedora.vm_export", {"vm_name": "preprod-01", "mode": "custom"}, {}),

    ("FEDORA/vm_export", "export personnalise",
     "exporte preprod-01 en mode personnalise",
     "fedora.vm_export", {"vm_name": "preprod-01", "mode": "custom"}, {}),

    ("FEDORA/vm_export", "emballe VM",
     "emballe sandbox-02",
     "fedora.vm_export", {"vm_name": "sandbox-02", "mode": "classic"}, {}),

    ("FEDORA/vm_export", "+ output_path",
     "exporte preprod-01 vers /mnt/exports",
     "fedora.vm_export", {"vm_name": "preprod-01"}, {"output_path": "/mnt/exports"}),

    ("FEDORA/vm_export", "+ force",
     "exporte de force preprod-01",
     "fedora.vm_export", {"vm_name": "preprod-01"}, {"force": True}),

    ("FEDORA/vm_export", "+ dry_run",
     "exporte preprod-01 en mode test dry-run",
     "fedora.vm_export", {"vm_name": "preprod-01"}, {"dry_run": True}),

    # ================================================================
    # FEDORA - vm_import
    # ================================================================
    ("FEDORA/vm_import", "importe archive",
     "importe /home/amineutron/vm-exports/preprod-01-export-20260227-classic.tar.gz",
     "fedora.vm_import", {"archive_path": "/home/amineutron/vm-exports/preprod-01-export-20260227-classic.tar.gz"}, {}),

    ("FEDORA/vm_import", "importe avec nouveau nom",
     "importe /home/amineutron/vm-exports/preprod-01-export-20260227-classic.tar.gz sous le nom test-import",
     "fedora.vm_import",
     {"archive_path": "/home/amineutron/vm-exports/preprod-01-export-20260227-classic.tar.gz", "new_name": "test-import"},
     {}),

    ("FEDORA/vm_import", "charge VM",
     "charge la vm depuis ~/vm-exports/system-clone-final-export-20260226-211346-classic.tar.gz",
     "fedora.vm_import", {"archive_path": "~/vm-exports/system-clone-final-export-20260226-211346-classic.tar.gz"}, {}),

    ("FEDORA/vm_import", "+ start apres import",
     "importe /tmp/test.tar.gz et demarre",
     "fedora.vm_import", {"archive_path": "/tmp/test.tar.gz"}, {"start": True}),

    ("FEDORA/vm_import", "+ dry_run",
     "importe /tmp/test.tar.gz en dry-run",
     "fedora.vm_import", {"archive_path": "/tmp/test.tar.gz"}, {"dry_run": True}),

    # ================================================================
    # BACKUP - backup_status
    # ================================================================
    ("BACKUP/status", "status backup",
     "status des backups",
     "fedora.backup_status", {}, {}),

    ("BACKUP/status", "etat backup",
     "etat des sauvegardes",
     "fedora.backup_status", {}, {}),

    ("BACKUP/status", "dashboard backup",
     "dashboard backup",
     "fedora.backup_status", {}, {}),

    ("BACKUP/status", "status sauvegarde",
     "status de mes sauvegardes",
     "fedora.backup_status", {}, {}),

    # ================================================================
    # BACKUP - backup_list
    # ================================================================
    ("BACKUP/list", "liste backups",
     "liste les backups",
     "fedora.backup_list", {}, {}),

    ("BACKUP/list", "affiche sauvegardes",
     "affiche mes sauvegardes",
     "fedora.backup_list", {}, {}),

    ("BACKUP/list", "montre backups",
     "montre les backups",
     "fedora.backup_list", {}, {}),

    ("BACKUP/list", "quelles sauvegardes",
     "quelles sont mes sauvegardes",
     "fedora.backup_list", {}, {}),

    ("BACKUP/list", "+ type timeshift",
     "liste les backups timeshift",
     "fedora.backup_list", {}, {"type": "timeshift"}),

    ("BACKUP/list", "+ type borg",
     "liste les sauvegardes borg",
     "fedora.backup_list", {}, {"type": "borg"}),

    ("BACKUP/list", "+ detailed",
     "liste les backups en detail",
     "fedora.backup_list", {}, {"detailed": True}),

    # ================================================================
    # BACKUP - backup_create
    # ================================================================
    ("BACKUP/create", "cree backup",
     "cree un backup",
     "fedora.backup_create", {}, {}),

    ("BACKUP/create", "fais sauvegarde",
     "fais une sauvegarde",
     "fedora.backup_create", {}, {}),

    ("BACKUP/create", "lance backup",
     "lance un backup",
     "fedora.backup_create", {}, {}),

    ("BACKUP/create", "backup de VM",
     "cree un backup de preprod-01",
     "fedora.backup_create", {}, {}),

    ("BACKUP/create", "+ type timeshift",
     "cree un backup timeshift",
     "fedora.backup_create", {}, {"type": "timeshift"}),

    ("BACKUP/create", "+ verify",
     "cree un backup et verifie",
     "fedora.backup_create", {}, {"verify": True}),

    ("BACKUP/create", "+ dry_run",
     "cree un backup en dry-run",
     "fedora.backup_create", {}, {"dry_run": True}),

    # ================================================================
    # BACKUP - backup_restore
    # ================================================================
    ("BACKUP/restore", "restaure backup",
     "restaure le backup",
     "fedora.backup_restore", {}, {}),

    ("BACKUP/restore", "restaure sauvegarde",
     "restaure ma sauvegarde",
     "fedora.backup_restore", {}, {}),

    ("BACKUP/restore", "restore alias",
     "restore le backup de preprod-01",
     "fedora.backup_restore", {}, {}),

    ("BACKUP/restore", "+ dry_run",
     "restaure le backup en dry-run",
     "fedora.backup_restore", {}, {"dry_run": True}),

    ("BACKUP/restore", "+ force",
     "restaure de force la sauvegarde",
     "fedora.backup_restore", {}, {"force": True}),

    # ================================================================
    # BACKUP - backup_verify
    # ================================================================
    ("BACKUP/verify", "verifie backup",
     "verifie le backup",
     "fedora.backup_verify", {}, {}),

    ("BACKUP/verify", "verifie sauvegarde",
     "verifie la sauvegarde",
     "fedora.backup_verify", {}, {}),

    ("BACKUP/verify", "controle backup",
     "controle le backup",
     "fedora.backup_verify", {}, {}),

    ("BACKUP/verify", "verifie backup VM",
     "verifie le backup de preprod-01",
     "fedora.backup_verify", {}, {}),

    ("BACKUP/verify", "+ deep",
     "verifie en profondeur le backup",
     "fedora.backup_verify", {}, {"deep": True}),

    ("BACKUP/verify", "+ quick",
     "verifie rapidement le backup",
     "fedora.backup_verify", {}, {"quick": True}),

    # ================================================================
    # BACKUP - backup_clean
    # ================================================================
    ("BACKUP/clean", "nettoie backups",
     "nettoie les backups",
     "fedora.backup_clean", {}, {}),

    ("BACKUP/clean", "purge sauvegardes",
     "purge les sauvegardes",
     "fedora.backup_clean", {}, {}),

    ("BACKUP/clean", "supprime anciens backups",
     "supprime les anciens backups",
     "fedora.backup_clean", {}, {}),

    ("BACKUP/clean", "efface backup",
     "efface les vieux backups",
     "fedora.backup_clean", {}, {}),

    ("BACKUP/clean", "+ dry_run",
     "nettoie les backups en dry-run",
     "fedora.backup_clean", {}, {"dry_run": True}),

    ("BACKUP/clean", "+ keep_last",
     "nettoie les backups garde les 3 derniers",
     "fedora.backup_clean", {}, {"keep_last": 3}),

    # ================================================================
    # DENON - power
    # ================================================================
    ("DENON/power", "allume denon",
     "allume le denon",
     "denon.power_on", {}, {}),

    ("DENON/power", "demarre denon",
     "demarre le denon",
     "denon.power_on", {}, {}),

    ("DENON/power", "eteins denon",
     "eteins le denon",
     "denon.power_off", {}, {}),

    ("DENON/power", "arrete denon",
     "arrete le denon",
     "denon.power_off", {}, {}),

    ("DENON/power", "stop denon",
     "stop le denon",
     "denon.power_off", {}, {}),

    # ================================================================
    # DENON - volume
    # ================================================================
    ("DENON/volume", "volume denon 44",
     "volume denon a 44",
     "denon.volume_set", {"level": 44}, {}),

    ("DENON/volume", "volume denon 50",
     "mets le volume denon a 50",
     "denon.volume_set", {"level": 50}, {}),

    ("DENON/volume", "monte volume denon",
     "monte le volume denon",
     "denon.volume_up", {}, {}),

    ("DENON/volume", "baisse volume denon",
     "baisse le volume denon",
     "denon.volume_down", {}, {}),

    ("DENON/volume", "50 de volume denon",
     "mets 50 de volume sur le denon",
     "denon.volume_set", {"level": 50}, {}),

    # ================================================================
    # DENON - mute
    # ================================================================
    ("DENON/mute", "mute denon",
     "mute le denon",
     "denon.mute_on", {}, {}),

    ("DENON/mute", "sourdine denon",
     "active la sourdine sur le denon",
     "denon.mute_on", {}, {}),

    ("DENON/mute", "coupe son denon",
     "coupe le son du denon",
     "denon.mute_on", {}, {}),

    ("DENON/mute", "demute denon",
     "demute le denon",
     "denon.mute_off", {}, {}),

    ("DENON/mute", "unmute denon",
     "unmute le denon",
     "denon.mute_off", {}, {}),

    ("DENON/mute", "desactive mute denon",
     "desactive le mute sur le denon",
     "denon.mute_off", {}, {}),

    # ================================================================
    # TV - power (RULE_MISS expected - pas dans les regles)
    # ================================================================
    ("TV/power", "allume TV",
     "allume la tv",
     "tv.power_on", {}, {}),

    ("TV/power", "eteins TV",
     "eteins la tele",
     "tv.power_off", {}, {}),

    ("TV/power", "TV en veille",
     "mets la tv en veille",
     "tv.power_off", {}, {}),

    # ================================================================
    # TV - volume (redirige vers DENON si HDMI ARC)
    # ================================================================
    ("TV/volume", "monte volume TV",
     "monte le volume de la tv",
     "tv.volume_up", {}, {}),

    ("TV/volume", "baisse volume TV",
     "baisse le son de la tele",
     "tv.volume_down", {}, {}),

    ("TV/volume", "volume TV 40",
     "mets le volume de la tv a 40",
     "tv.volume_set", {}, {}),

    ("TV/volume", "mute TV",
     "mets la tv en muet",
     "tv.mute", {}, {}),

    # ================================================================
    # TV - applications
    # ================================================================
    ("TV/app", "lance Netflix sur TV",
     "lance netflix sur la tv",
     "tv.launch_app", {}, {}),

    ("TV/app", "ouvre YouTube TV",
     "ouvre youtube sur la tele",
     "tv.launch_app", {}, {}),

    ("TV/app", "youtube video",
     "joue cette video youtube sur la tv https://youtu.be/dQw4w9WgXcQ",
     "tv.youtube_video", {}, {}),

    # ================================================================
    # TV - ambilight
    # ================================================================
    ("TV/ambilight", "allume ambilight",
     "allume l ambilight",
     "tv.ambilight_on", {}, {}),

    ("TV/ambilight", "eteins ambilight",
     "eteins l ambilight",
     "tv.ambilight_off", {}, {}),

    ("TV/ambilight", "ambilight couleur",
     "mets l ambilight en bleu",
     "tv.ambilight_color", {}, {}),

    # ================================================================
    # HUE - turn_on_group (dans les regles)
    # ================================================================
    ("HUE/group", "allume lumieres",
     "allume les lumieres",
     "hue.turn_on_group", {"group_id": 81}, {}),

    ("HUE/group", "allume toutes lumieres",
     "allume toutes les lumieres",
     "hue.turn_on_group", {"group_id": 81}, {}),

    ("HUE/group", "eteins lumieres groupe",
     "eteins les lumieres",
     "hue.turn_off_group", {"group_id": 81}, {}),

    # ================================================================
    # HUE - turn_on/off_light (dans les regles pour off)
    # ================================================================
    ("HUE/light", "eteins lumiere bureau",
     "eteins la lumiere bureau",
     "hue.turn_off_light", {}, {}),

    ("HUE/light", "eteins lumiere salon",
     "eteins la lumiere salon",
     "hue.turn_off_light", {}, {}),

    ("HUE/light", "allume lumiere chevet",
     "allume la lumiere chevet",
     "hue.turn_on_light", {}, {}),  # RULE_MISS

    # ================================================================
    # HUE - brightness / color (RULE_MISS)
    # ================================================================
    ("HUE/brightness", "luminosite 50%",
     "mets la luminosite a 50 pour cent",
     "hue.set_brightness", {}, {}),

    ("HUE/brightness", "lumiere plus forte",
     "mets les lumieres plus fortes",
     "hue.set_brightness", {}, {}),

    ("HUE/color", "couleur rouge",
     "mets les lumieres en rouge",
     "hue.set_color_rgb", {}, {}),

    ("HUE/color", "ambiance bleue",
     "mets une ambiance bleue",
     "hue.set_color_rgb", {}, {}),

    # ================================================================
    # HUE - scene
    # ================================================================
    ("HUE/scene", "active scene relax",
     "active la scene relax",
     "hue.activate_scene_by_name", {}, {}),

    ("HUE/scene", "scene lecture",
     "lance la scene lecture",
     "hue.activate_scene_by_name", {}, {}),

    # ================================================================
    # Edge cases - collisions et cas limites
    # ================================================================
    ("EDGE/collision", "start ne matche pas TV",
     "lance netflix sur la tv",
     "tv.launch_app", {}, {}),  # ne doit PAS declencher vm_start

    ("EDGE/collision", "stop ne matche pas backup",
     "status des backups",
     "fedora.backup_status", {}, {}),

    ("EDGE/collision", "verifie backup vs vm",
     "verifie le backup de preprod-01",
     "fedora.backup_verify", {}, {}),  # backup_verify avant vm_verify

    ("EDGE/collision", "supprime backups vs vm",
     "supprime les anciens backups",
     "fedora.backup_clean", {}, {}),  # backup_clean avant vm_destroy

    ("EDGE/collision", "clone systeme vs clone normal",
     "clone systeme neutron en backup",
     "fedora.vm_clone_system", {}, {}),  # vm_clone_system avant vm_clone

    ("EDGE/args", "export mode exam syntaxe alternative",
     "exporte system-clone-final en mode examen",
     "fedora.vm_export", {"vm_name": "system-clone-final", "mode": "exam"}, {}),

    ("EDGE/args", "import avec renommage",
     "importe /home/amineutron/vm-exports/test.tar.gz sous le nom ma-vm",
     "fedora.vm_import", {"new_name": "ma-vm"}, {}),

    ("EDGE/args", "vm_status global vs specifique",
     "status de preprod-01",
     "fedora.vm_status", {"vm_name": "preprod-01"}, {}),

    ("EDGE/args", "snapshot sans nom VM",
     "cree un snapshot",
     None, {}, {}),  # doit demander clarification

    ("EDGE/args", "copie chemin complexe",
     "copie /home/amineutron/projet/config.json vers sandbox-02",
     "fedora.vm_copy", {"source": "/home/amineutron/projet/config.json", "vm_name": "sandbox-02"}, {}),

    ("EDGE/args", "exec commande avec espaces",
     "execute apt-get update sur preprod-01",
     "fedora.vm_exec", {"vm_name": "preprod-01", "command": "apt-get update"}, {}),

    ("EDGE/args", "export custom synonyme sur-mesure",
     "exporte preprod-01 en mode sur-mesure",
     "fedora.vm_export", {"vm_name": "preprod-01", "mode": "custom"}, {}),

    ("EDGE/args", "export custom synonyme choix",
     "exporte preprod-01 avec choix des operations",
     "fedora.vm_export", {"vm_name": "preprod-01", "mode": "custom"}, {}),

]

# ============================================================
# Runner
# ============================================================

def normalize(q):
    """Normalise la query comme le fait _rule_based_detect."""
    q = unicodedata.normalize('NFD', q.lower())
    return ''.join(c for c in q if unicodedata.category(c) != 'Mn')


def tool_matches(result_tool, expected_tool):
    """Compare les noms d'outils avec ou sans prefixe serveur."""
    if expected_tool is None:
        return result_tool is None
    if result_tool is None:
        return False
    r = result_tool.split(".")[-1] if "." in result_tool else result_tool
    e = expected_tool.split(".")[-1] if "." in expected_tool else expected_tool
    return r == e


def check_args(result_args, mandatory, optional):
    """Verifie les arguments. Retourne (mandatory_ok, missing_optional)."""
    if result_args is None:
        result_args = {}
    missing_mandatory = []
    for k, v in mandatory.items():
        rv = result_args.get(k)
        if rv is None:
            missing_mandatory.append(k)
        elif v != "" and str(rv) != str(v):
            missing_mandatory.append(f"{k}={v}(got={rv})")
    missing_optional = [k for k in optional if k not in result_args]
    return missing_mandatory, missing_optional


def run_tests():
    categories = {}
    results = []

    PASS = "PASS"
    PARTIAL = "PARTIAL"
    FAIL = "FAIL"
    RULE_MISS = "RULE_MISS"

    for cat, desc, query, expected_tool, mandatory_args, optional_args in TESTS:
        raw_q = normalize(query)
        analysis = Pipeline._rule_based_detect(raw_q)
        if analysis is not None:
            analysis = Pipeline._enrich_optional_args(raw_q, analysis)

        result_tool = analysis.tool if analysis else None
        result_args = analysis.arguments if analysis else {}

        tool_ok = tool_matches(result_tool, expected_tool)
        missing_mand, missing_opt = check_args(result_args, mandatory_args, optional_args)

        if expected_tool is None:
            # On attend que rien ne matche (clarification requise)
            status = PASS if result_tool is None else FAIL
        elif result_tool is None:
            status = RULE_MISS
        elif not tool_ok:
            status = FAIL
        elif missing_mand:
            status = FAIL
        elif missing_opt:
            status = PARTIAL
        else:
            status = PASS

        entry = {
            "cat": cat, "desc": desc, "query": query,
            "expected_tool": expected_tool, "result_tool": result_tool,
            "result_args": result_args, "mandatory_args": mandatory_args,
            "missing_mand": missing_mand, "missing_opt": missing_opt,
            "status": status
        }
        results.append(entry)
        categories.setdefault(cat.split("/")[0], []).append(entry)

    return results, categories


def print_report(results, categories):
    G = "\033[32m"
    Y = "\033[33m"
    R = "\033[31m"
    B = "\033[34m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"

    STATUS_COLOR = {
        "PASS": G, "PARTIAL": Y, "FAIL": R, "RULE_MISS": B
    }

    print(f"\n{BOLD}{'='*70}{RESET}")
    print(f"{BOLD}  CAMPAGNE DE TESTS MCP - LYRA RAG v2{RESET}")
    print(f"{BOLD}{'='*70}{RESET}\n")

    # Detail par test
    current_cat = None
    for r in results:
        cat_group = r["cat"].split("/")[0]
        if cat_group != current_cat:
            current_cat = cat_group
            print(f"\n{BOLD}--- {cat_group} ---{RESET}")

        sc = r["status"]
        color = STATUS_COLOR[sc]
        pad = r["desc"][:35].ljust(36)
        tool_str = (r["result_tool"] or "NONE").split(".")[-1][:18].ljust(19)
        args_str = ""
        if r["missing_mand"]:
            args_str = f" {R}ARGS_MANQUANTS={r['missing_mand']}{RESET}"
        elif r["missing_opt"]:
            args_str = f" {Y}OPT_MISS={r['missing_opt']}{RESET}"

        print(f"  {color}[{sc:<9}]{RESET} {DIM}{pad}{RESET} -> {tool_str}{args_str}")

    # Score par categorie
    print(f"\n{BOLD}{'='*70}{RESET}")
    print(f"{BOLD}  SCORES PAR CATEGORIE{RESET}")
    print(f"{BOLD}{'='*70}{RESET}")
    total_pass = total_partial = total_fail = total_miss = 0

    for cat_name, entries in sorted(categories.items()):
        n = len(entries)
        p = sum(1 for e in entries if e["status"] == "PASS")
        pa = sum(1 for e in entries if e["status"] == "PARTIAL")
        f = sum(1 for e in entries if e["status"] == "FAIL")
        m = sum(1 for e in entries if e["status"] == "RULE_MISS")
        total_pass += p; total_partial += pa; total_fail += f; total_miss += m
        score_pct = round(100 * (p + 0.5 * pa) / n) if n else 0
        bar = f"{G}{'#' * (p)}{Y}{'~' * pa}{B}{'?' * m}{R}{'-' * f}{RESET}"
        print(f"  {BOLD}{cat_name:<8}{RESET} {bar} "
              f"{G}{p}P{RESET} {Y}{pa}~{RESET} {B}{m}?{RESET} {R}{f}F{RESET} "
              f"/ {n}  [{score_pct}%]")

    total = len(results)
    score_final = round(100 * (total_pass + 0.5 * total_partial) / total)
    print(f"\n{BOLD}{'='*70}{RESET}")
    print(f"{BOLD}  SCORE FINAL : {G}{total_pass}{RESET}{BOLD} PASS  "
          f"{Y}{total_partial}{RESET}{BOLD} PARTIAL  "
          f"{B}{total_miss}{RESET}{BOLD} RULE_MISS  "
          f"{R}{total_fail}{RESET}{BOLD} FAIL  / {total} tests{RESET}")
    print(f"{BOLD}  POURCENTAGE : {score_final}%{RESET}  "
          f"{DIM}(PASS=1pt, PARTIAL=0.5pt, RULE_MISS/FAIL=0pt){RESET}")

    print(f"\n{BOLD}  LEGENDE:{RESET}")
    print(f"  {G}[PASS]     {RESET} Outil correct + tous les args attendus")
    print(f"  {Y}[PARTIAL]  {RESET} Outil correct + args obligatoires OK + args optionnels manquants")
    print(f"  {B}[RULE_MISS]{RESET} Aucune regle ne matche -> ira vers EPHAISTOS en production")
    print(f"  {R}[FAIL]     {RESET} Mauvais outil ou arg obligatoire manquant\n")

    # Rapport texte brut pour PDF/NotebookLM
    return generate_text_report(results, categories, total_pass, total_partial, total_fail, total_miss, total, score_final)


def generate_text_report(results, categories, total_pass, total_partial, total_fail, total_miss, total, score_final):
    lines = []
    lines.append("CAMPAGNE DE TESTS MCP - LYRA RAG v2")
    lines.append("=" * 70)
    lines.append("")
    lines.append("OBJECTIF")
    lines.append("--------")
    lines.append("Tester la detection outil + extraction arguments du pipeline Lyra")
    lines.append("via _rule_based_detect(), sans executer aucun script reel.")
    lines.append("")
    lines.append("LEGENDE")
    lines.append("-------")
    lines.append("PASS      : Outil correct + tous les args attendus presens")
    lines.append("PARTIAL   : Outil correct + args obligatoires OK + args optionnels manquants")
    lines.append("RULE_MISS : Aucune regle ne matche (ira vers EPHAISTOS en production)")
    lines.append("FAIL      : Mauvais outil ou arg obligatoire manquant")
    lines.append("")
    lines.append("RESULTATS DETAILLES")
    lines.append("-------------------")

    current_cat = None
    for r in results:
        cat_group = r["cat"].split("/")[0]
        if cat_group != current_cat:
            current_cat = cat_group
            lines.append("")
            lines.append(f"=== {cat_group} ===")

        status = r["status"]
        desc = r["desc"]
        query = r["query"]
        result_tool = r["result_tool"] or "NONE"
        expected_tool = r["expected_tool"] or "NONE"
        result_args = r["result_args"]
        missing_mand = r["missing_mand"]
        missing_opt = r["missing_opt"]

        lines.append(f"[{status:<9}] {desc}")
        lines.append(f"  Requete   : \"{query}\"")
        lines.append(f"  Attendu   : {expected_tool}")
        lines.append(f"  Obtenu    : {result_tool}")
        if result_args:
            lines.append(f"  Args      : {result_args}")
        if missing_mand:
            lines.append(f"  FAIL args : {missing_mand}")
        if missing_opt:
            lines.append(f"  PARTIAL   : args optionnels manquants : {missing_opt}")

    lines.append("")
    lines.append("SCORES PAR CATEGORIE")
    lines.append("--------------------")
    for cat_name, entries in sorted(categories.items()):
        n = len(entries)
        p = sum(1 for e in entries if e["status"] == "PASS")
        pa = sum(1 for e in entries if e["status"] == "PARTIAL")
        f = sum(1 for e in entries if e["status"] == "FAIL")
        m = sum(1 for e in entries if e["status"] == "RULE_MISS")
        score_pct = round(100 * (p + 0.5 * pa) / n) if n else 0
        lines.append(f"  {cat_name:<10} : {p} PASS  {pa} PARTIAL  {m} RULE_MISS  {f} FAIL  / {n} tests  [{score_pct}%]")

    lines.append("")
    lines.append("SCORE FINAL")
    lines.append("-----------")
    lines.append(f"  PASS      : {total_pass}")
    lines.append(f"  PARTIAL   : {total_partial}")
    lines.append(f"  RULE_MISS : {total_miss}")
    lines.append(f"  FAIL      : {total_fail}")
    lines.append(f"  TOTAL     : {total} tests")
    lines.append(f"  SCORE     : {score_final}%")
    lines.append("")
    lines.append("ANALYSE")
    lines.append("-------")
    lines.append("Les RULE_MISS correspondent aux outils TV, HUE (sauf turn_on/off_group/light)")
    lines.append("qui ne sont pas couverts par _rule_based_detect.")
    lines.append("Ces requetes sont traitees par EPHAISTOS (LLM) en production.")
    lines.append("Les PARTIAL indiquent des args optionnels mentionnes dans la requete mais non")
    lines.append("extraits par les regles (attendu - les regles n'extraient pas tous les params).")

    return "\n".join(lines)


if __name__ == "__main__":
    results, categories = run_tests()
    report_text = print_report(results, categories)

    # Sauvegarder le rapport texte
    report_path = Path(__file__).parent / "test_campaign_report.txt"
    report_path.write_text(report_text, encoding="utf-8")
    print(f"Rapport sauvegarde : {report_path}")
