"""Couverture des outils sans regle (lyra#24), testee sur le registre complet.

Le registre applique le premier module qui correspond : ces tests verifient a la fois
la nouvelle regle et qu'aucun module place avant elle (vm, catt, tracking) ne la capte.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from lyra.rules import detect


def route(q):
    r = detect(q)
    return (r.tool, r.arguments) if r else (None, {})


# ---------------------------------------------------------------- luminosite
# Regression : « les lumieres a 50% » partait vers hue.set_brightness sans light_id
# (obligatoire : l'appel echouait) et l'echelle etait 0-255 alors que Hue va de 0 a 254.
@pytest.mark.parametrize("q,brightness", [
    ("mets les lumieres a 50%", 127),
    ("luminosite a 50%", 127),
    ("lumieres a 80 pour cent", 203),
    ("luminosite a 100%", 254),
    ("luminosite a 0%", 0),
])
def test_luminosite_du_groupe(q, brightness):
    assert route(q) == ("hue.set_group_brightness", {"group_id": 81, "brightness": brightness})


@pytest.mark.parametrize("q,brightness", [
    ("monte la luminosite", 200),
    ("baisse la luminosite", 50),
    ("lumieres plus douces", 50),
])
def test_luminosite_relative_du_groupe(q, brightness):
    assert route(q) == ("hue.set_group_brightness", {"group_id": 81, "brightness": brightness})


# ---------------------------------------------------------------- hue beat
@pytest.mark.parametrize("q,args", [
    ("lance hue beat", {}),
    ("demarre le hue beat en mode fire", {"palette": "fire"}),
    ("active hue beat palette neon", {"palette": "neon"}),
    ("lance le hue beat ironman", {"palette": "ironman"}),
])
def test_hue_beat_start(q, args):
    assert route(q) == ("hue.hue_beat_start", args)


@pytest.mark.parametrize("q", ["arrete hue beat", "stop le hue beat", "coupe hue beat"])
def test_hue_beat_stop(q):
    assert route(q)[0] == "hue.hue_beat_stop"


@pytest.mark.parametrize("q", ["etat du hue beat", "hue beat tourne ?", "est ce que hue beat est actif"])
def test_hue_beat_status(q):
    assert route(q)[0] == "hue.hue_beat_status"


# ---------------------------------------------------------------- lectures hue
@pytest.mark.parametrize("q", ["liste les lumieres", "quelles lampes sont allumees", "affiche mes lampes"])
def test_get_all_lights(q):
    assert route(q)[0] == "hue.get_all_lights"


@pytest.mark.parametrize("q", ["liste les groupes de lumieres", "quels groupes hue"])
def test_get_all_groups(q):
    assert route(q)[0] == "hue.get_all_groups"


@pytest.mark.parametrize("q,light", [("fais clignoter la lampe 3", 3), ("identifie la lampe 2", 2)])
def test_alert_light(q, light):
    assert route(q) == ("hue.alert_light", {"light_id": light})


@pytest.mark.parametrize("q,preset", [
    ("lumiere chaude", "warm"),
    ("mets une lumiere froide", "cool"),
    ("lumieres froides", "cool"),
    ("lumiere du jour", "daylight"),
])
def test_teinte_du_groupe(q, preset):
    assert route(q) == ("hue.set_group_color_preset", {"group_id": 81, "preset": preset})


@pytest.mark.parametrize("q", [
    "une lumiere plus froide au bureau", "une lumiere plus chaude dans la chambre", "mets une lumiere plus froide",
])
def test_teinte_relative_laissee_au_modele(q):
    # « plus chaude / plus froide » decale la temperature (hue.set_color_temperature,
    # jeux hors regles 2, 4 et 5) : la regle du preset de groupe ne doit pas l'attraper
    hit = route(q)
    assert hit is None or hit[0] != "hue.set_group_color_preset"


def test_ambiance_nommee_reste_une_scene():
    # « ambiance concentration » peut etre une scene Hue du meme nom : pas de preset impose
    assert route("lance la scene concentration")[0] == "hue.activate_scene_by_name"


# ---------------------------------------------------------------- cast, tv, fedora
@pytest.mark.parametrize("q", ["infos sur la video en cours", "donne moi les infos du media en cours",
                               "c'est quoi qui passe sur le chromecast"])
def test_cast_info(q):
    assert route(q)[0] == "catt.cast_info"


@pytest.mark.parametrize("q", ["quelles applis sur la tele", "liste les applications de la tv"])
def test_tv_list_apps(q):
    assert route(q)[0] == "tv.list_apps"


@pytest.mark.parametrize("q,key", [
    ("appuie sur retour", "Back"),
    ("touche home sur la tele", "Home"),
    ("appuie sur ok", "Confirm"),
    ("touche bas sur la tv", "CursorDown"),
])
def test_tv_send_key(q, key):
    assert route(q) == ("tv.send_key", {"key": key})


def test_touche_inconnue_ne_devine_pas():
    assert route("appuie sur la touche magique")[0] != "tv.send_key"


@pytest.mark.parametrize("q", ["aide fedora", "qu'est ce que tu sais faire sur les vm"])
def test_fedora_help(q):
    assert route(q)[0] == "fedora.help"
