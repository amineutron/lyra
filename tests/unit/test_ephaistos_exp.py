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


# --- Iteration 2 --------------------------------------------------------------

class TestNormalisation:
    def test_accents_et_ponctuation(self):
        assert exp.normaliser("Éteins l'Ambilight, vite !") == ["eteins", "l", "ambilight", "vite"]

    def test_tokens_outil(self):
        assert exp.tokens_outil("tv.ambilight_on") == {"tv", "ambilight", "on"}


class TestCarteMots:
    def test_ambilight_devant_power(self):
        specs = ["tv.power_on: power_on()", "tv.ambilight_on: ambilight_on()"]
        assert exp.boost_mots(specs, "allume l ambilight")[0].startswith("tv.ambilight_on")

    def test_veille_designe_off(self):
        specs = ["tv.get_state: get_state()", "tv.power_on: power_on()", "tv.power_off: power_off()"]
        assert exp.boost_mots(specs, "mets la tv en veille")[0].startswith("tv.power_off")

    def test_chevet_designe_light_pas_ambilight(self):
        """"light" est une sous-chaine de "ambilight" : la comparaison se fait par token."""
        assert exp.score_mots("tv.ambilight_on", "allume la lumiere chevet") == 0
        assert exp.score_mots("hue.turn_on_light", "allume la lumiere chevet") == 1

    def test_url_designe_youtube_pas_navigateur(self):
        specs = ["catt.cast_browser: cast_browser(url)", "catt.cast_youtube: cast_youtube(url)"]
        r = exp.boost_mots(specs, "caste cette video https://youtu.be/x")
        assert r[0].startswith("catt.cast_youtube")

    def test_tri_stable_sans_mot_cible(self):
        specs = ["a.x: x()", "b.y: y()", "c.z: z()"]
        assert exp.boost_mots(specs, "fais quelque chose") == specs


class TestUrl:
    def test_detecte(self):
        assert exp.contient_url("joue https://youtu.be/dQw4w9WgXcQ sur la tv")
        assert exp.contient_url("ouvre http://example.org")

    def test_absente(self):
        assert not exp.contient_url("ouvre youtube sur la tele")
        assert not exp.contient_url("")


class TestLexical:
    DOCS = [
        ("tv.ambilight_on", "Active l'Ambilight de la TV"),
        ("tv.power_off", "Eteint la TV Philips (standby) | Utilise pour: éteindre la télé. éteins la télévision"),
        ("catt.cast_resume", "Reprend la lecture du cast"),
        ("hue.turn_on_light", "Turn on a specific light by name | Utilise pour: allumer la lampe de chevet"),
    ]

    def _index(self):
        return exp.RechercheLexicale([d for _, d in self.DOCS],
                                     [{"tool_name": n, "server_name": n.split(".")[0].upper()} for n, _ in self.DOCS])

    def test_mot_rare_en_tete(self):
        r = self._index().chercher("allume l ambilight")
        assert r[0]["metadata"]["tool_name"] == "tv.ambilight_on"

    def test_sans_accent_retrouve_le_doc_accentue(self):
        r = self._index().chercher("eteins la tele")
        assert r[0]["metadata"]["tool_name"] == "tv.power_off"

    def test_nom_de_l_outil_compte(self):
        """"cast_resume" n'a pas "cast" dans sa description : le nom l'apporte."""
        r = self._index().chercher("reprends le cast")
        assert r[0]["metadata"]["tool_name"] == "catt.cast_resume"

    def test_format_et_score_borne(self):
        r = self._index().chercher("chevet")
        assert r and r[0]["source"] == "lexical" and 0 < r[0]["score"] <= 0.5

    def test_corpus_vide(self):
        assert exp.RechercheLexicale([], []).chercher("x") == []


class TestFusionRRF:
    def _item(self, nom, score, source="capabilities"):
        return {"document": f"doc {nom}", "metadata": {"tool_name": nom}, "score": score, "source": source}

    def test_present_dans_les_deux_listes_gagne(self):
        sem = [self._item("a", 0.9), self._item("b", 0.8)]
        lex = [self._item("b", 0.5, "lexical"), self._item("c", 0.4, "lexical")]
        assert [_["metadata"]["tool_name"] for _ in exp.fusion_rrf(sem, lex)] == ["b", "a", "c"]

    def test_score_semantique_conserve(self):
        sem = [self._item("a", 0.9)]
        lex = [self._item("a", 0.5, "lexical")]
        r = exp.fusion_rrf(sem, lex)
        assert r[0]["score"] == 0.9 and r[0]["score_rrf"] > 0

    def test_doublons_semantiques_fusionnes(self):
        """capabilities + parameters du meme outil ne comptent qu'une fois."""
        sem = [self._item("a", 0.9), self._item("a", 0.7, "parameters"), self._item("b", 0.8)]
        assert len(exp.fusion_rrf(sem, [])) == 2

    def test_liste_lexicale_vide(self):
        sem = [self._item("a", 0.9)]
        assert exp.fusion_rrf(sem, [])[0]["metadata"]["tool_name"] == "a"
