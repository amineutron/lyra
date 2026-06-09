"""Tests unitaires pour lyra/rules/denon.py."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from lyra.rules.denon import detect


def tool(q):
    r = detect(q)
    return r.tool if r else None


def args(q):
    r = detect(q)
    return r.arguments if r else {}


# ------------------------------------------------------------------ #
# power_on / power_off                                                #
# ------------------------------------------------------------------ #

class TestPowerOn:
    def test_allume_denon(self):
        assert tool("allume le denon") == "denon.power_on"

    def test_demarre_denon(self):
        assert tool("demarre le denon") == "denon.power_on"

    def test_active_denon(self):
        assert tool("active le denon") == "denon.power_on"


class TestPowerOff:
    def test_eteins_denon(self):
        assert tool("eteins le denon") == "denon.power_off"

    def test_arrete_denon(self):
        assert tool("arrete le denon") == "denon.power_off"

    def test_no_volume_collision(self):
        # "eteins le son du denon" a "son" -> power_off exclu, retourne None
        # (mute_on requiert "mute/sourdine/silence" ou "coupe le son")
        assert tool("eteins le son du denon") is None
        # "coupe le son du denon" -> mute_on
        assert tool("coupe le son du denon") == "denon.mute_on"


# ------------------------------------------------------------------ #
# mute_on / mute_off / mute_toggle                                    #
# ------------------------------------------------------------------ #

class TestMuteOn:
    def test_mute_denon(self):
        assert tool("mute le denon") == "denon.mute_on"

    def test_sourdine_denon(self):
        assert tool("sourdine denon") == "denon.mute_on"

    def test_coupe_son_denon(self):
        assert tool("coupe le son du denon") == "denon.mute_on"

    def test_silence_denon(self):
        assert tool("silence denon") == "denon.mute_on"


class TestMuteOff:
    def test_demute_denon(self):
        assert tool("demute le denon") == "denon.mute_off"

    def test_unmute_denon(self):
        assert tool("unmute le denon") == "denon.mute_off"

    def test_reactive_son_denon(self):
        assert tool("reactive le son du denon") == "denon.mute_off"

    def test_enleve_mute_denon(self):
        assert tool("enleve le mute denon") == "denon.mute_off"


class TestMuteToggle:
    def test_toggle_mute_denon(self):
        assert tool("toggle le mute denon") == "denon.mute_toggle"

    def test_bascule_mute_denon(self):
        assert tool("bascule le mute du denon") == "denon.mute_toggle"

    def test_inverse_mute_denon(self):
        assert tool("inverse le mute denon") == "denon.mute_toggle"

    def test_toggle_before_mute_on(self):
        # toggle doit matcher AVANT mute_on (ordre dans detect())
        assert tool("toggle denon") == "denon.mute_toggle"


# ------------------------------------------------------------------ #
# get_status                                                          #
# ------------------------------------------------------------------ #

class TestGetStatus:
    def test_status_denon(self):
        assert tool("status du denon") == "denon.get_status"

    def test_etat_denon(self):
        assert tool("etat du denon") == "denon.get_status"

    def test_infos_denon(self):
        assert tool("infos denon") == "denon.get_status"

    def test_no_number_collision(self):
        # "volume denon a 50" -> volume_set, pas get_status
        assert tool("volume denon a 50") == "denon.volume_set"


# ------------------------------------------------------------------ #
# set_input                                                           #
# ------------------------------------------------------------------ #

class TestSetInput:
    def test_source_bluray(self):
        assert tool("change la source denon en bluray") == "denon.set_input"

    def test_input_tv(self):
        assert tool("source denon en tv") == "denon.set_input"

    def test_input_extracted_bd(self):
        a = args("change la source denon en bluray")
        assert a.get("input") == "BD"

    def test_input_game(self):
        a = args("source denon en jeu")
        assert a.get("input") == "GAME"

    def test_input_sat(self):
        a = args("passe en satellite denon")
        assert a.get("input") == "SAT/CBL"

    def test_input_dvd(self):
        a = args("entree dvd denon")
        assert a.get("input") == "DVD"

    def test_input_mediaplayer(self):
        a = args("source denon media player")
        assert a.get("input") == "MPLAY"


# ------------------------------------------------------------------ #
# volume_set / volume_up / volume_down                                #
# ------------------------------------------------------------------ #

class TestVolumeSet:
    def test_volume_denon_a_50(self):
        assert tool("volume denon a 50") == "denon.volume_set"

    def test_level_extracted(self):
        a = args("volume denon a 44")
        assert a.get("level") == 44

    def test_passe_volume_30(self):
        assert tool("passe le volume denon a 30") == "denon.volume_set"


class TestVolumeUp:
    def test_monte_volume_denon(self):
        assert tool("monte le volume du denon") == "denon.volume_up"

    def test_augmente_son_denon(self):
        assert tool("augmente le son denon") == "denon.volume_up"


class TestVolumeDown:
    def test_baisse_volume_denon(self):
        assert tool("baisse le volume du denon") == "denon.volume_down"

    def test_diminue_son_denon(self):
        assert tool("diminue le son denon") == "denon.volume_down"


# ------------------------------------------------------------------ #
# Pas de match sans "denon"                                           #
# ------------------------------------------------------------------ #

class TestNoMatch:
    def test_sans_denon(self):
        # Sans le mot "denon", aucune regle ne match
        assert tool("monte le volume") is None

    def test_vm_query(self):
        assert tool("demarre preprod-01") is None

    def test_empty(self):
        assert tool("") is None
