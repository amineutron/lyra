"""Tests unitaires pour lyra/rules/tv.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest

from lyra.rules import detect as detect_all
from lyra.rules.tv import detect


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
    def test_allume_tv(self):
        assert tool("allume la tv") == "tv.power_on"

    def test_allume_tele(self):
        assert tool("allume la tele") == "tv.power_on"

    def test_demarrer_television(self):
        assert tool("demarre la television") == "tv.power_on"

    def test_no_app_collision(self):
        # "allume netflix sur la tv" -> launch_app, pas power_on
        assert tool("allume netflix sur la tv") == "tv.launch_app"


class TestPowerOff:
    def test_eteins_tv(self):
        assert tool("eteins la tv") == "tv.power_off"

    def test_veille_tele(self):
        assert tool("mets la tele en veille") == "tv.power_off"

    def test_standby(self):
        assert tool("standby tv") == "tv.power_off"

    def test_no_volume_collision(self):
        # "eteins le volume de la tv" -> non power_off
        assert tool("eteins le volume de la tv") != "tv.power_off"


# ------------------------------------------------------------------ #
# sound_only / screen_off / screen_on                                 #
# ------------------------------------------------------------------ #

class TestSoundOnly:
    def test_son_seul(self):
        assert tool("son seul") == "tv.screen_off"

    def test_mode_musique(self):
        assert tool("mode musique") == "tv.screen_off"

    def test_mode_audio(self):
        assert tool("mode audio") == "tv.screen_off"

    def test_musique_seulement(self):
        assert tool("musique seulement") == "tv.screen_off"


class TestScreenOff:
    def test_eteins_ecran(self):
        assert tool("eteins l'ecran") == "tv.screen_off"

    def test_coupe_dalle(self):
        assert tool("coupe la dalle") == "tv.screen_off"

    def test_desactive_affichage(self):
        assert tool("desactive l'affichage") == "tv.screen_off"

    def test_veille_ecran(self):
        # "mets en veille" requiert que les mots soient adjacents dans la regle
        assert tool("coupe l'ecran") == "tv.screen_off"


class TestScreenOn:
    def test_rallume_ecran(self):
        assert tool("rallume l'ecran") == "tv.screen_on"

    def test_reactive_affichage(self):
        assert tool("reactive l'affichage") == "tv.screen_on"


# ------------------------------------------------------------------ #
# mute                                                                #
# ------------------------------------------------------------------ #

class TestMute:
    def test_mute_tv(self):
        assert tool("mute la tv") == "tv.mute"

    def test_sourdine_tv(self):
        assert tool("sourdine tv") == "tv.mute"

    def test_coupe_son_tv(self):
        assert tool("coupe le son de la tv") == "tv.mute"

    def test_silence_tv(self):
        assert tool("silence tv") == "tv.mute"


# ------------------------------------------------------------------ #
# volume_set / volume_up / volume_down                                #
# ------------------------------------------------------------------ #

class TestVolumeSet:
    def test_volume_tv_a_45(self):
        assert tool("volume tv a 45") == "tv.volume_set"

    def test_level_extracted(self):
        a = args("volume tv a 45")
        assert a.get("level") == 45

    def test_mets_volume_30(self):
        assert tool("mets le volume a 30 sur la tv") == "tv.volume_set"


class TestVolumeUp:
    def test_monte_volume_tv(self):
        assert tool("monte le volume de la tv") == "tv.volume_up"

    def test_augmente_son_tv(self):
        assert tool("augmente le son de la tv") == "tv.volume_up"


class TestVolumeDown:
    def test_baisse_son_tv(self):
        assert tool("baisse le son de la tv") == "tv.volume_down"

    def test_diminue_volume_tv(self):
        assert tool("diminue le volume de la tv") == "tv.volume_down"


# ------------------------------------------------------------------ #
# launch_app                                                          #
# ------------------------------------------------------------------ #

class TestLaunchApp:
    def test_lance_netflix(self):
        assert tool("lance netflix sur la tv") == "tv.launch_app"

    def test_ouvre_youtube_tv(self):
        assert tool("ouvre youtube sur la tv") == "tv.launch_app"

    def test_app_extracted(self):
        a = args("lance netflix sur la tv")
        assert a.get("app") == "netflix"

    def test_plex_tv(self):
        assert tool("ouvre plex sur la tele") == "tv.launch_app"


# ------------------------------------------------------------------ #
# ambilight                                                           #
# ------------------------------------------------------------------ #

class TestAmbilightOn:
    def test_allume_ambilight(self):
        assert tool("allume l'ambilight") == "tv.ambilight_on"

    def test_active_ambilight(self):
        assert tool("active l'ambilight") == "tv.ambilight_on"


class TestAmbilightOff:
    def test_eteins_ambilight(self):
        assert tool("eteins l'ambilight") == "tv.ambilight_off"

    def test_coupe_ambilight(self):
        assert tool("coupe l'ambilight") == "tv.ambilight_off"


class TestAmbilightColor:
    """pylips-mcp 0.4.0 expose tv.ambilight_color(r, g, b) : une couleur nommee donne
    son RVB. Avant, la regle se rabattait sur ambilight_mode(manual), sans effet sur
    la 55OLED705 qui n'a pas de style FOLLOW_COLOR (pylips-mcp#7)."""

    @pytest.mark.parametrize("phrase,rgb", [
        ("ambilight en rouge", (255, 0, 0)),
        ("ambilight bleu", (0, 0, 255)),
        ("mets l'ambilight en bleu", (0, 0, 255)),
        ("ambilight couleur verte", (0, 255, 0)),
        ("mets l ambilight en couleur bleue", (0, 0, 255)),
        ("passe les leds de la tele en violet", (128, 0, 128)),
        ("ambilight orange", (255, 165, 0)),
        ("ambilight en jaune", (255, 255, 0)),
        ("mets l'ambilight en rose", (255, 192, 203)),
        ("ambilight en cyan", (0, 255, 255)),
        ("ambilight turquoise", (64, 224, 208)),
        ("ambilight en magenta", (255, 0, 255)),
    ])
    def test_couleur_nommee_donne_son_rgb(self, phrase, rgb):
        r = detect(phrase)
        assert r is not None and r.tool == "tv.ambilight_color", phrase
        assert (r.arguments["r"], r.arguments["g"], r.arguments["b"]) == rgb

    def test_mode_manuel_explicite_reste_un_mode(self):
        r = detect("ambilight en mode manuel")
        assert r is not None and r.tool == "tv.ambilight_mode"
        assert r.arguments == {"mode": "manual"}

    def test_regression_hue_ne_prend_plus_la_couleur_de_l_ambilight(self):
        # "couleur" faisait matcher hue.set_group_color_rgb avant la regle TV
        assert detect_all("ambilight couleur verte").tool == "tv.ambilight_color"
        assert detect_all("mets les lumieres en vert").tool == "hue.set_group_color_rgb"


# ------------------------------------------------------------------ #
# Pas de match                                                        #
# ------------------------------------------------------------------ #

class TestNoMatch:
    def test_vm_query(self):
        assert tool("demarre preprod-01") is None

    def test_hue_query(self):
        assert tool("allume les lumieres") is None

    def test_empty(self):
        assert tool("") is None


# Regression 2026-08-11 : meme bug que hue (blanche?/violette? ratait les
# masculins) — l'ambilight tombait sur ambilight_on au lieu de la couleur.
class TestAmbilightCouleursMasculines:
    def test_ambilight_blanc(self):
        r = detect("mets l ambilight en blanc")
        assert r is not None and r.tool == "tv.ambilight_color"
        assert r.arguments == {"r": 255, "g": 255, "b": 255}

    def test_ambilight_violet(self):
        r = detect("ambilight en violet")
        assert r is not None and r.tool == "tv.ambilight_color"

    def test_paradigme_complet(self):
        """Chaque cle du dictionnaire de couleurs doit declencher la regle."""
        from lyra.rules.tv import _AMBI_COLOR_MAP
        for color, rgb in _AMBI_COLOR_MAP.items():
            r = detect(f"ambilight en {color}")
            assert r is not None and r.tool == "tv.ambilight_color", color
            assert (r.arguments["r"], r.arguments["g"], r.arguments["b"]) == rgb, color


class TestPhrasesInedites:
    """Regression lyra#22 : "mode musique" sur les leds n'est pas le mode son seul de la TV."""

    def test_leds_en_mode_musique_ne_coupent_pas_l_image(self):
        r = detect("passe les leds de la tele en mode musique")
        assert r is not None and r.tool == "tv.ambilight_mode"
        assert r.arguments.get("mode") == "follow_audio"

    def test_ambilight_mode_video(self):
        r = detect("mets l'ambilight en mode video")
        assert r is not None and r.tool == "tv.ambilight_mode" and r.arguments.get("mode") == "follow_video"

    def test_mode_musique_sans_leds_reste_son_seul(self):
        assert tool("mets la tele en mode musique") == "tv.screen_off"


class TestQuestionsEtat:
    """Regression lyra#23 : une question d'etat n'est pas un ordre d'extinction."""

    def test_une_question_ne_coupe_pas_la_tele(self):
        for q in ("est-ce que la tele est en veille", "la tele est en veille ?", "est-ce que la tv est allumee"):
            r = detect(q)
            assert r is None or r.tool == "tv.get_state", (q, r and r.tool)


class TestJeu4:
    """"il est tard" n'est pas une question d'etat (controle du jeu 4)."""

    def test_on_eteint_la_tele_il_est_tard(self):
        r = detect("on eteint la tele, il est tard")
        assert r is None or r.tool == "tv.power_off", r and r.tool

    def test_question_d_etat_avec_il_est(self):
        r = detect("la tele, il est en veille ?")
        assert r is not None and r.tool == "tv.get_state"


class TestJeu5:
    def test_ambilight_qui_suit_la_musique(self):
        r = detect("l'ambilight qui suit la musique")
        assert r.tool == "tv.ambilight_mode" and r.arguments == {"mode": "follow_audio"}

    def test_ambilight_cale_sur_la_video(self):
        r = detect("cale l'ambilight sur la video")
        assert r.tool == "tv.ambilight_mode" and r.arguments == {"mode": "follow_video"}


class TestJeu6:
    def test_eteindre_les_leds_de_la_tele_est_ambilight_off(self):
        assert tool("eteins les leds de la tele") == "tv.ambilight_off"
        assert tool("allume les leds de la tele") == "tv.ambilight_on"

    def test_eteindre_la_tele_reste_power_off(self):
        assert tool("eteins la tele") == "tv.power_off"

    def test_leds_sans_verbe_va_au_modele(self):
        assert tool("les leds de la tele, tu me les enleves") == "tv.ambilight_off"
        assert tool("vire les leds de la tele") == "tv.ambilight_off"
        assert tool("les leds de la tele en ambiance lounge") == "tv.ambilight_mode"
        assert detect("les leds de la tele") is None


class TestCasseDesUrl:
    def test_id_youtube_garde_sa_casse(self):
        assert args("mets cette video sur la tele https://www.youtube.com/watch?v=jNQXAC9IVRw") == {"video": "https://www.youtube.com/watch?v=jNQXAC9IVRw"}
