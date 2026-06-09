"""Tests unitaires pour lyra/rules/tracking.py."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from lyra.rules.tracking import detect


def tool(q):
    r = detect(q)
    return r.tool if r else None


def args(q):
    r = detect(q)
    return r.arguments if r else {}


# ------------------------------------------------------------------ #
# kill_task                                                           #
# ------------------------------------------------------------------ #

class TestKillTask:
    def test_kill_tache_id(self):
        assert tool("kill tache abc123") == "tracking.kill_task"

    def test_annule_tache(self):
        assert tool("annule la tache abc1234") == "tracking.kill_task"

    def test_stop_tache(self):
        assert tool("stop la tache xyz9876") == "tracking.kill_task"

    def test_identifier_extracted(self):
        a = args("kill tache abc1234")
        assert a.get("identifier") == "abc1234"

    def test_tue_tache(self):
        assert tool("tue la tache abc1234") == "tracking.kill_task"

    def test_kill_sans_mot_tache(self):
        # Sans "tache" explicite, l'ID doit etre >= 4 chars
        assert tool("kill preprod-01") == "tracking.kill_task"


# ------------------------------------------------------------------ #
# tracking.delete                                                     #
# ------------------------------------------------------------------ #

class TestDelete:
    def test_supprime_tache(self):
        assert tool("supprime la tache abc1234 dans le tracking") == "tracking.delete"

    def test_session_id_extracted(self):
        a = args("supprime tache abc1234 dans le tracking")
        assert a.get("session_id") == "abc1234"

    def test_efface_tache_tracking(self):
        assert tool("efface la tache abc12345 du tracking") == "tracking.delete"


# ------------------------------------------------------------------ #
# tracking.get                                                        #
# ------------------------------------------------------------------ #

class TestGet:
    def test_statut_tache(self):
        assert tool("statut tache abc1234 tracking") == "tracking.get"

    def test_session_id_extracted(self):
        a = args("statut tache abc1234 tracking")
        assert a.get("session_id") == "abc1234"

    def test_avancement_tracking(self):
        assert tool("avancement abc123456 tracking") == "tracking.get"


# ------------------------------------------------------------------ #
# tracking.list                                                       #
# ------------------------------------------------------------------ #

class TestList:
    def test_taches_en_cours(self):
        assert tool("taches en cours") == "tracking.list"

    def test_quoi_en_cours(self):
        assert tool("quoi en cours") == "tracking.list"

    def test_liste_mes_taches(self):
        assert tool("liste mes taches") == "tracking.list"

    def test_quoi_tourne(self):
        assert tool("quoi tourne") == "tracking.list"

    def test_template_and_status(self):
        a = args("taches en cours")
        assert a.get("template") == "lyra_task"
        assert a.get("status") == "running"

    def test_tracking_taches_actives(self):
        assert tool("tracking taches actives") == "tracking.list"


# ------------------------------------------------------------------ #
# tracking.open_ui                                                    #
# ------------------------------------------------------------------ #

class TestOpenUi:
    def test_affiche_tracking(self):
        assert tool("affiche le tracking") == "tracking.open_ui"

    def test_ouvre_dashboard(self):
        assert tool("ouvre le dashboard tracking") == "tracking.open_ui"

    def test_montre_tracking(self):
        assert tool("montre le tracking") == "tracking.open_ui"

    def test_filter_errors(self):
        a = args("affiche les erreurs tracking")
        assert a.get("filter_template") == "errors"

    def test_filter_lyra(self):
        a = args("affiche le suivi lyra tracking")
        assert a.get("filter_template") == "lyra_task"


# ------------------------------------------------------------------ #
# Pas de match                                                        #
# ------------------------------------------------------------------ #

class TestNoMatch:
    def test_vm_query(self):
        assert tool("demarre preprod-01") is None

    def test_empty(self):
        assert tool("") is None
