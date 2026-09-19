"""Tests unitaires pour lyra/rules/catt.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from lyra.rules.catt import detect


def tool(q):
    r = detect(q)
    return r.tool if r else None


def args(q):
    r = detect(q)
    return r.arguments if r else {}


# ------------------------------------------------------------------ #
# cast_scan                                                           #
# ------------------------------------------------------------------ #

class TestCastScan:
    def test_scan_cast(self):
        assert tool("scan les appareils cast") == "catt.cast_scan"

    def test_cherche_chromecast(self):
        assert tool("cherche les chromecast") == "catt.cast_scan"

    def test_liste_devices(self):
        assert tool("liste les devices cast") == "catt.cast_scan"

    def test_detecte_appareils_diffusion(self):
        assert tool("detecte les appareils diffuse") == "catt.cast_scan"

    def test_trouve_cast(self):
        assert tool("trouve les appareils cast") == "catt.cast_scan"


# ------------------------------------------------------------------ #
# cast_volume                                                         #
# ------------------------------------------------------------------ #

class TestCastVolume:
    def test_monte_volume_cast(self):
        assert tool("monte le volume du cast") == "catt.cast_volume"

    def test_baisse_volume_chromecast(self):
        assert tool("baisse le volume du chromecast") == "catt.cast_volume"

    def test_volume_diffusion_a_50(self):
        assert tool("volume diffusion a 50") == "catt.cast_volume"

    def test_level_extracted(self):
        a = args("volume cast a 60")
        assert a.get("level") == 60

    def test_no_level_optional(self):
        a = args("monte le volume du cast")
        assert a.get("level") is None


# ------------------------------------------------------------------ #
# cast_youtube                                                        #
# ------------------------------------------------------------------ #

class TestCastYoutube:
    def test_caste_url_youtube(self):
        q = "caste cette video https://youtu.be/abc123"
        assert tool(q) == "catt.cast_youtube"

    def test_url_extracted(self):
        q = "diffuse https://www.youtube.com/watch?v=abc123 sur la tv"
        a = args(q)
        assert "youtube" in a.get("url", "")

    def test_youtu_be_short(self):
        q = "envoie https://youtu.be/pAgnJDJN4VA sur le cast"
        assert tool(q) == "catt.cast_youtube"

    def test_no_verb_no_match(self):
        # URL sans verbe cast -> ne match pas cast_youtube
        assert tool("https://youtu.be/abc123") is None


# ------------------------------------------------------------------ #
# cast_stop                                                           #
# ------------------------------------------------------------------ #

class TestCastStop:
    def test_arrete_cast(self):
        assert tool("arrete le cast") == "catt.cast_stop"

    def test_stop_diffusion(self):
        assert tool("stop la diffusion") == "catt.cast_stop"

    def test_stoppe_chromecast(self):
        assert tool("stoppe le chromecast") == "catt.cast_stop"


# ------------------------------------------------------------------ #
# cast_pause                                                          #
# ------------------------------------------------------------------ #

class TestCastPause:
    def test_pause_cast(self):
        assert tool("pause le cast") == "catt.cast_pause"

    def test_mets_cast_en_pause(self):
        assert tool("mets le cast en pause") == "catt.cast_pause"

    def test_pause_diffusion(self):
        assert tool("pause la diffusion") == "catt.cast_pause"


# ------------------------------------------------------------------ #
# cast_resume                                                         #
# ------------------------------------------------------------------ #

class TestCastResume:
    def test_reprends_cast(self):
        assert tool("reprends le cast") == "catt.cast_resume"

    def test_continue_diffusion(self):
        assert tool("continue la diffusion") == "catt.cast_resume"

    def test_relance_cast(self):
        assert tool("relance le cast") == "catt.cast_resume"


# ------------------------------------------------------------------ #
# cast_seek                                                           #
# ------------------------------------------------------------------ #

class TestCastSeek:
    def test_avance_30_secondes(self):
        assert tool("avance de 30 secondes") == "catt.cast_seek"

    def test_seek_seconds_extracted(self):
        a = args("avance de 30 secondes")
        assert a.get("seek_seconds") == 30

    def test_recule_negatif(self):
        a = args("recule de 15 secondes")
        assert a.get("seek_seconds") == -15

    def test_avance_2_minutes(self):
        a = args("avance de 2 minutes")
        assert a.get("seek_seconds") == 120

    def test_recule_1_min(self):
        a = args("recule de 1 min")
        assert a.get("seek_seconds") == -60


# ------------------------------------------------------------------ #
# Pas de match                                                        #
# ------------------------------------------------------------------ #

class TestNoMatch:
    def test_vm_query(self):
        assert tool("demarre preprod-01") is None

    def test_tv_volume(self):
        assert tool("volume tv a 30") is None

    def test_empty(self):
        assert tool("") is None


class TestUrlSurLeCast:
    """Regression lyra#23 : une URL destinee au chromecast/a la tele est un cast, pas un navigateur."""

    def test_url_youtube_sur_le_chromecast(self):
        r = detect("mets ca sur le chromecast https://youtu.be/aAbBcCdDeE0")
        assert r is not None and r.tool == "catt.cast_youtube" and r.arguments.get("url", "").startswith("https://youtu.be/")

    def test_flux_quelconque_sur_la_tele(self):
        r = detect("mets ce flux sur la tele https://example.org/stream.m3u8")
        assert r is not None and r.tool == "catt.cast_url"


class TestDualStop:
    """Regression lyra#23 : arreter le dual cast n'est pas cast_stop."""

    def test_arrete_le_dual_cast(self):
        r = detect("arrete le dual cast")
        assert r is not None and r.tool == "catt.cast_dual_stop"

    def test_arrete_le_cast_reste_cast_stop(self):
        r = detect("arrete le cast")
        assert r is not None and r.tool == "catt.cast_stop"


class TestOngletSurLaTele:
    """Regression lyra#23 : « envoie l'onglet firefox sur la tele » est un cast du navigateur, pas une app a ouvrir."""

    def test_onglet_firefox_sur_la_tele(self):
        r = detect("envoie l'onglet firefox sur la tele")
        assert r is not None and r.tool == "catt.cast_browser"
