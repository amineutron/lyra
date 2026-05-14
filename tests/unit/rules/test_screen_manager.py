"""Tests unitaires pour lyra/rules/screen_manager.py."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from lyra.rules.screen_manager import detect


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def tool(q):
    r = detect(q)
    return r.tool if r else None

def args(q):
    r = detect(q)
    return r.arguments if r else {}


# ------------------------------------------------------------------ #
# list_screens                                                         #
# ------------------------------------------------------------------ #

class TestListScreens:
    def test_quels_ecrans(self):
        assert tool("quels sont mes ecrans") == "screen-manager.list_screens"

    def test_liste_moniteurs(self):
        assert tool("liste les moniteurs") == "screen-manager.list_screens"

    def test_combien_ecrans(self):
        assert tool("combien d'ecrans j'ai") == "screen-manager.list_screens"

    def test_affiche_ecrans(self):
        assert tool("affiche mes ecrans") == "screen-manager.list_screens"

    def test_montre_displays(self):
        assert tool("montre les displays") == "screen-manager.list_screens"

    def test_donne_liste_affichages(self):
        assert tool("donne moi la liste des affichages") == "screen-manager.list_screens"


# ------------------------------------------------------------------ #
# list_apps                                                            #
# ------------------------------------------------------------------ #

class TestListApps:
    def test_liste_applications(self):
        assert tool("liste les applications") == "screen-manager.list_apps"

    def test_quelles_apps(self):
        assert tool("quelles apps sont disponibles") == "screen-manager.list_apps"

    def test_liste_applis(self):
        assert tool("donne moi la liste des applis") == "screen-manager.list_apps"

    def test_quels_programmes(self):
        assert tool("quels programmes j'ai") == "screen-manager.list_apps"

    def test_logiciels_disponibles(self):
        assert tool("quels logiciels sont disponibles") == "screen-manager.list_apps"


# ------------------------------------------------------------------ #
# setup_screens                                                        #
# ------------------------------------------------------------------ #

class TestSetupScreens:
    def test_configure_ecrans(self):
        assert tool("configure les ecrans") == "screen-manager.setup_screens"

    def test_detecte_moniteurs(self):
        assert tool("detecte mes moniteurs") == "screen-manager.setup_screens"

    def test_setup_displays(self):
        assert tool("setup les displays") == "screen-manager.setup_screens"

    def test_initialise_ecrans(self):
        assert tool("initialise mes ecrans") == "screen-manager.setup_screens"

    def test_parametre_affichage(self):
        assert tool("parametre les affichages") == "screen-manager.setup_screens"


# ------------------------------------------------------------------ #
# update_screen_config                                                 #
# ------------------------------------------------------------------ #

class TestUpdateScreenConfig:
    def test_renomme_ecran_2(self):
        assert tool("renomme l'ecran 2 en bureau") == "screen-manager.update_screen_config"

    def test_renomme_ecran_index_et_alias(self):
        r = detect("renomme l'ecran 2 en bureau")
        assert r is not None
        assert r.arguments.get("screen_index") == 2
        assert r.arguments.get("alias") == "bureau"

    def test_change_alias_moniteur(self):
        assert tool("change l'alias du moniteur 1") == "screen-manager.update_screen_config"

    def test_appelle_ecran(self):
        assert tool("appelle l'ecran 3 tele") == "screen-manager.update_screen_config"


# ------------------------------------------------------------------ #
# open_url                                                             #
# ------------------------------------------------------------------ #

class TestOpenUrl:
    def test_ouvre_url_sur_ecran(self):
        assert tool("ouvre https://worldmonitor.app sur le grand ecran") == "screen-manager.open_url"

    def test_affiche_localhost(self):
        assert tool("affiche localhost:3000 sur l'ecran de droite") == "screen-manager.open_url"

    def test_url_extraite(self):
        r = detect("ouvre https://google.com sur le moniteur")
        assert r is not None
        assert "https://google.com" in r.arguments.get("url", "")

    def test_url_sans_ecran(self):
        # URL sans destination - screen optionnel
        assert tool("lance https://worldmonitor.app") == "screen-manager.open_url"

    def test_url_sur_tele(self):
        assert tool("affiche https://worldmonitor.app sur la tele") == "screen-manager.open_url"


# ------------------------------------------------------------------ #
# open_app                                                             #
# ------------------------------------------------------------------ #

class TestOpenApp:
    def test_ouvre_firefox_ecran(self):
        assert tool("ouvre firefox sur le 2e ecran") == "screen-manager.open_app"

    def test_lance_btop_gauche(self):
        assert tool("lance btop sur l'ecran de gauche") == "screen-manager.open_app"

    def test_affiche_app_tele(self):
        assert tool("affiche worldmonitor sur la tele") == "screen-manager.open_app"

    def test_mets_chrome_moniteur(self):
        assert tool("mets chrome sur le moniteur principal") == "screen-manager.open_app"

    def test_projette_app_ecran(self):
        assert tool("projette terminal sur le 3e ecran") == "screen-manager.open_app"

    def test_envoie_app_ecran(self):
        assert tool("envoie firefox sur l'ecran de droite") == "screen-manager.open_app"

    def test_app_name_extrait(self):
        r = detect("ouvre firefox sur le 2e ecran")
        assert r is not None
        assert r.arguments.get("app_name") == "firefox"

    def test_screen_extrait(self):
        r = detect("lance btop sur l'ecran de gauche")
        assert r is not None
        assert "gauche" in r.arguments.get("screen", "")

    def test_bascule_app_ecran(self):
        assert tool("bascule firefox sur l'ecran principal") == "screen-manager.open_app"

    def test_deplace_app_ecran(self):
        assert tool("deplace la fenetre sur le moniteur de droite") == "screen-manager.open_app"

    def test_formulation_naturelle_milieu(self):
        assert tool("ouvre chrome sur l'ecran du milieu") == "screen-manager.open_app"

    def test_formulation_numero(self):
        assert tool("lance vscode sur l'ecran 3") == "screen-manager.open_app"


# ------------------------------------------------------------------ #
# Pas de match attendu (non-regression)                               #
# ------------------------------------------------------------------ #

class TestNoMatch:
    def test_demarre_vm(self):
        # vm_start ne doit pas etre capture par screen_manager
        assert tool("demarre preprod-01") is None

    def test_allume_lumieres(self):
        assert tool("allume les lumieres") is None

    def test_volume_denon(self):
        assert tool("monte le volume") is None

    def test_question_generique(self):
        assert tool("c'est quoi un ecran ?") is None

    def test_backup_create(self):
        assert tool("cree un backup de preprod-01") is None


# ------------------------------------------------------------------ #
# Regressions - collisions avec d'autres regles                       #
# ------------------------------------------------------------------ #

class TestRegressions:
    def test_lance_sur_ecran_pas_vm_start(self):
        """'lance worldmonitor sur l'ecran de droite' -> open_app, pas vm_start"""
        from lyra.rules.vm import detect as vm_detect
        assert vm_detect("lance worldmonitor sur l'ecran de droite") is None

    def test_open_app_worldmonitor(self):
        assert tool("lance worldmonitor sur l'ecran de droite") == "screen-manager.open_app"

    def test_open_app_firefox_droite(self):
        assert tool("lance firefox sur l'ecran de droite") == "screen-manager.open_app"

    def test_vm_start_sans_ecran_toujours_ok(self):
        """'lance preprod-01' sans contexte ecran reste vm_start"""
        from lyra.rules.vm import detect as vm_detect
        r = vm_detect("lance preprod-01")
        assert r is not None
        assert r.tool == "fedora.vm_start"

    def test_demarre_vm_sans_ecran_toujours_ok(self):
        from lyra.rules.vm import detect as vm_detect
        r = vm_detect("demarre sandbox-02")
        assert r is not None
        assert r.tool == "fedora.vm_start"

    def test_open_app_avec_tele(self):
        """'lance worldmonitor sur la tele' -> open_app"""
        assert tool("lance worldmonitor sur la tele") == "screen-manager.open_app"

    def test_vm_start_avec_tele_mot_cle_tv(self):
        """'lance la tv' -> exclu de vm_start (mot-cle TV)"""
        from lyra.rules.vm import detect as vm_detect
        r = vm_detect("lance la tv")
        # Si match, vm_name ne doit pas etre 'tv'
        if r is not None:
            assert r.arguments.get("vm_name", "") != "tv"
