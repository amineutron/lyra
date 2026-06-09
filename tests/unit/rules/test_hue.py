"""Tests unitaires pour lyra/rules/hue.py."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from lyra.rules.hue import detect


def tool(q):
    r = detect(q)
    return r.tool if r else None


def args(q):
    r = detect(q)
    return r.arguments if r else {}


# ------------------------------------------------------------------ #
# activate_scene_by_name                                              #
# ------------------------------------------------------------------ #

class TestActivateScene:
    def test_lance_scene(self):
        assert tool("lance la scene cozy") == "hue.activate_scene_by_name"

    def test_active_scene(self):
        assert tool("active la scene manga") == "hue.activate_scene_by_name"

    def test_scene_name_extracted(self):
        a = args("lance la scene cozy")
        assert a.get("scene_name") == "cozy"

    def test_scene_sur_groupe(self):
        a = args("mets la scene relax sur les lumieres")
        assert tool("mets la scene relax sur les lumieres") == "hue.activate_scene_by_name"
        assert a.get("scene_name") == "relax"

    def test_applique_scene(self):
        assert tool("applique la scene cinema") == "hue.activate_scene_by_name"


# ------------------------------------------------------------------ #
# get_all_scenes                                                       #
# ------------------------------------------------------------------ #

class TestGetAllScenes:
    def test_liste_scenes(self):
        assert tool("liste les scenes") == "hue.get_all_scenes"

    def test_quelles_ambiances(self):
        assert tool("quelles ambiances j'ai") == "hue.get_all_scenes"

    def test_affiche_scenes(self):
        assert tool("affiche mes scenes") == "hue.get_all_scenes"

    def test_scenes_disponibles(self):
        assert tool("scenes disponibles") == "hue.get_all_scenes"


# ------------------------------------------------------------------ #
# turn_on_group                                                        #
# ------------------------------------------------------------------ #

class TestTurnOnGroup:
    def test_allume_les_lumieres(self):
        assert tool("allume les lumieres") == "hue.turn_on_group"

    def test_allume_toutes_les_lampes(self):
        assert tool("allume toutes les lampes") == "hue.turn_on_group"

    def test_group_id_81(self):
        a = args("allume les lumieres")
        assert a.get("group_id") == 81

    def test_allumez_lumieres(self):
        assert tool("allumez les lumieres") == "hue.turn_on_group"


# ------------------------------------------------------------------ #
# turn_off_group                                                       #
# ------------------------------------------------------------------ #

class TestTurnOffGroup:
    def test_eteins_les_lumieres(self):
        assert tool("eteins les lumieres") == "hue.turn_off_group"

    def test_eteins_toutes_lampes(self):
        assert tool("eteins toutes les lampes") == "hue.turn_off_group"

    def test_group_id_81(self):
        a = args("eteins les lumieres")
        assert a.get("group_id") == 81

    def test_coupe_lumieres(self):
        assert tool("coupe les lumieres") == "hue.turn_off_group"


# ------------------------------------------------------------------ #
# turn_on_light / turn_off_light                                      #
# ------------------------------------------------------------------ #

class TestTurnOnLight:
    def test_allume_lumiere_bureau(self):
        assert tool("allume la lumiere bureau") == "hue.turn_on_light"

    def test_light_name_extracted(self):
        a = args("allume la lumiere salon")
        assert a.get("light_name") == "salon"

    def test_allume_lampe(self):
        assert tool("allume la lampe cuisine") == "hue.turn_on_light"


class TestTurnOffLight:
    def test_eteins_lumiere_bureau(self):
        assert tool("eteins la lumiere bureau") == "hue.turn_off_light"

    def test_light_name_extracted(self):
        a = args("eteins la lumiere salon")
        assert a.get("light_name") == "salon"


# ------------------------------------------------------------------ #
# set_brightness                                                       #
# ------------------------------------------------------------------ #

class TestSetBrightness:
    def test_luminosite_pct(self):
        assert tool("luminosite a 50%") == "hue.set_brightness"

    def test_luminosite_value(self):
        a = args("luminosite a 50%")
        assert a.get("brightness") == 127  # 50 * 255 // 100

    def test_lumieres_a_80_pct(self):
        assert tool("lumieres a 80 pour cent") == "hue.set_brightness"

    def test_monte_luminosite(self):
        assert tool("monte la luminosite") == "hue.set_brightness"

    def test_baisse_luminosite(self):
        assert tool("baisse la luminosite") == "hue.set_brightness"

    def test_lumieres_plus_douces(self):
        assert tool("lumieres plus douces") == "hue.set_brightness"


# ------------------------------------------------------------------ #
# set_color_rgb                                                        #
# ------------------------------------------------------------------ #

class TestSetColorRgb:
    def test_lumieres_en_rouge(self):
        assert tool("lumieres en rouge") == "hue.set_color_rgb"

    def test_ambiance_bleue(self):
        assert tool("ambiance bleue") == "hue.set_color_rgb"

    def test_rouge_rgb(self):
        a = args("lumieres en rouge")
        assert a == {"r": 255, "g": 0, "b": 0}

    def test_bleu_rgb(self):
        a = args("lumieres en bleu")
        assert a == {"r": 0, "g": 0, "b": 255}

    def test_couleur_orange(self):
        assert tool("couleur orange") == "hue.set_color_rgb"


# ------------------------------------------------------------------ #
# Pas de match                                                        #
# ------------------------------------------------------------------ #

class TestNoMatch:
    def test_vm_query(self):
        assert tool("demarre preprod-01") is None

    def test_tv_query(self):
        assert tool("allume la tv") is None

    def test_empty(self):
        assert tool("") is None
