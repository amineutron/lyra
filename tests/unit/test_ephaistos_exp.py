"""Variantes experimentales d'EPHAISTOS (logique pure, sans modele)."""


import pytest

from lyra.models import ephaistos_exp as exp
from lyra.models.ephaistos import EPHAISTOS_SYSTEM_PROMPT as PROMPT


@pytest.fixture(autouse=True)
def _env_propre(monkeypatch):
    monkeypatch.delenv("LYRA_EXP", raising=False)


class TestActivation:
    def test_rien_par_defaut(self):
        assert exp.actives() == set()

    def test_lit_la_variable(self, monkeypatch):
        monkeypatch.setenv("LYRA_EXP", "dedup, routage ,inconnue")
        assert exp.actives() == {"dedup", "routage"}


class TestExemplesCibles:
    def test_ne_garde_que_les_blocs_demandes(self):
        r = exp.exemples_cibles(PROMPT, {"catt"})
        assert "=== EXEMPLES CATT" in r
        assert "=== EXEMPLES FEDORA" not in r
        assert "=== EXEMPLES HUE" not in r
        assert r.startswith(PROMPT[:200])          # l'en-tete est conserve

    def test_plusieurs_serveurs(self):
        r = exp.exemples_cibles(PROMPT, {"tv", "hue"})
        assert "=== EXEMPLES TV" in r and "=== EXEMPLES HUE" in r
        assert "=== EXEMPLES CATT" not in r

    def test_aucun_serveur_reconnu_rend_le_prompt_complet(self):
        assert exp.exemples_cibles(PROMPT, set()) == PROMPT
        assert exp.exemples_cibles(PROMPT, {"inconnu"}) == PROMPT

    def test_reduit_vraiment_la_taille(self):
        assert len(exp.exemples_cibles(PROMPT, {"catt"})) < len(PROMPT) / 4


class TestSpecs:
    SPECS = ["catt.cast_stop: cast_stop()", "tv.power_on: power_on()",
             "catt.cast_stop: cast_stop()", "catt.cast_pause: cast_pause()"]

    def test_serveurs(self):
        assert exp.serveurs_des_specs(self.SPECS) == {"catt", "tv"}

    def test_dedup_garde_la_premiere_et_l_ordre(self):
        assert exp.dedupliquer(self.SPECS) == [self.SPECS[0], self.SPECS[1], self.SPECS[3]]

    def test_numerotation(self):
        assert exp.numeroter(self.SPECS[:2]) == ["1. catt.cast_stop: cast_stop()",
                                                 "2. tv.power_on: power_on()"]


class TestIndex:
    SPECS = ["catt.cast_stop: cast_stop()", "tv.power_on: power_on()"]

    def test_numero_valide(self):
        assert exp.resoudre_index("2", self.SPECS) == "tv.power_on"
        assert exp.resoudre_index(1, self.SPECS) == "catt.cast_stop"
        assert exp.resoudre_index(" 1. ", self.SPECS) == "catt.cast_stop"

    def test_numero_hors_borne_rendu_tel_quel(self):
        assert exp.resoudre_index("9", self.SPECS) == "9"

    def test_nom_non_numerique_inchange(self):
        assert exp.resoudre_index("cast_stop", self.SPECS) == "cast_stop"

    def test_none(self):
        assert exp.resoudre_index(None, self.SPECS) is None
