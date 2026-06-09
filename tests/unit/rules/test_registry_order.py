"""Tests de l'ordre critique du registre lyra/rules/__init__.py.

L'ordre _REGISTRY est load-bearing : un changement d'ordre provoque
des faux positifs silencieux. Ces tests le verifient explicitement.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from lyra.rules import detect


def tool(q):
    r = detect(q)
    return r.tool if r else None


# ------------------------------------------------------------------ #
# IRONMAN en premier                                                  #
# ------------------------------------------------------------------ #

class TestIronmanFirst:
    def test_je_suis_iron_man_vers_ironman(self):
        # Doit aller vers ironman, pas vers vm_start
        assert tool("je suis iron man") == "ironman.run_scene"

    def test_lance_iron_man_vers_ironman(self):
        # "lance" sans contexte VM -> ironman (pas vm_start)
        assert tool("lance iron man") == "ironman.run_scene"


# ------------------------------------------------------------------ #
# BACKUP avant VM                                                     #
# ------------------------------------------------------------------ #

class TestBackupBeforeVm:
    def test_verifie_backup_de_vm(self):
        # "verifie backup" -> backup_verify (pas vm_verify)
        assert tool("verifie backup de preprod-01") == "fedora.backup_verify"

    def test_verifie_sauvegarde(self):
        # "verifie la sauvegarde" -> backup_verify
        assert tool("verifie la sauvegarde") == "fedora.backup_verify"

    def test_status_backup_pas_vm(self):
        # "status backup" -> backup_status
        assert tool("status backup") == "fedora.backup_status"


# ------------------------------------------------------------------ #
# TRACKING apres VM                                                   #
# ------------------------------------------------------------------ #

class TestTrackingAfterVm:
    def test_taches_en_cours_tracking(self):
        # "taches en cours" -> tracking.list (pas vm_status)
        assert tool("taches en cours") == "tracking.list"

    def test_affiche_tracking(self):
        assert tool("affiche le tracking") == "tracking.open_ui"


# ------------------------------------------------------------------ #
# HUE apres TRACKING - scenes avant vm_start                         #
# ------------------------------------------------------------------ #

class TestHueScenesBeforeVmStart:
    def test_lance_scene_vers_hue(self):
        # "lance la scene cozy" -> hue.activate_scene_by_name (pas vm_start)
        assert tool("lance la scene cozy") == "hue.activate_scene_by_name"

    def test_allume_les_lumieres_vers_hue(self):
        # "allume les lumieres" -> hue.turn_on_group (pas tv.power_on)
        assert tool("allume les lumieres") == "hue.turn_on_group"


# ------------------------------------------------------------------ #
# TV separe de HUE                                                    #
# ------------------------------------------------------------------ #

class TestTvSeparateFromHue:
    def test_allume_tv_vers_tv(self):
        # "allume la tv" -> tv.power_on (pas hue)
        assert tool("allume la tv") == "tv.power_on"

    def test_eteins_tele_vers_tv(self):
        assert tool("eteins la tele") == "tv.power_off"


# ------------------------------------------------------------------ #
# DENON gate strict (requiert "denon" dans la phrase)                 #
# ------------------------------------------------------------------ #

class TestDenonGate:
    def test_volume_sans_denon_ne_matche_pas_denon(self):
        # "monte le volume" sans "denon" -> TV ou None (pas denon)
        result = tool("monte le volume")
        assert result != "denon.volume_up"

    def test_volume_avec_denon_matche_denon(self):
        assert tool("monte le volume du denon") == "denon.volume_up"

    def test_mute_avec_denon_matche_denon(self):
        assert tool("mute le denon") == "denon.mute_on"


# ------------------------------------------------------------------ #
# SOUND_ONLY sans contexte TV requis                                  #
# ------------------------------------------------------------------ #

class TestSoundOnlyNoTvRequired:
    def test_son_seul_sans_tv(self):
        # "son seul" ne necessite pas "tv" dans la phrase
        assert tool("son seul") == "tv.sound_only"

    def test_mode_musique_sans_tv(self):
        assert tool("mode musique") == "tv.sound_only"
