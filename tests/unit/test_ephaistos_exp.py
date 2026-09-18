"""Variantes experimentales d'EPHAISTOS (logique pure, sans modele)."""


import pytest

from lyra.models import ephaistos_exp as exp
from lyra.models.ephaistos import EPHAISTOS_SYSTEM_PROMPT as PROMPT


@pytest.fixture(autouse=True)
def _env_propre(monkeypatch):
    monkeypatch.delenv("LYRA_EXP", raising=False)


class TestActivation:
    def test_variable_absente_donne_la_configuration_retenue(self):
        assert exp.actives() == set(exp.DEFAUT)
        assert set(exp.DEFAUT) <= set(exp.VARIANTES)

    def test_variable_vide_desactive_tout(self, monkeypatch):
        """LYRA_EXP="" est le comportement d'avant la boucle (bench_boucle s'en sert)."""
        monkeypatch.setenv("LYRA_EXP", "")
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


class TestLexicalSansDependance:
    def test_sans_rank_bm25_la_recherche_se_degrade_sans_lever(self, monkeypatch):
        """CI du 2026-09-17 : ModuleNotFoundError en pleine cascade. Le repli doit etre silencieux."""
        import sys
        monkeypatch.setitem(sys.modules, "rank_bm25", None)   # import -> ImportError
        idx = exp.RechercheLexicale(["doc"], [{"tool_name": "a.b"}])
        assert idx.disponible is False
        assert idx.chercher("doc") == []
        assert exp.fusion_rrf([{"document": "x", "metadata": {"tool_name": "a.b"}, "score": 0.5}], idx.chercher("doc"))


class TestLexical:
    @pytest.fixture(autouse=True)
    def _bm25_present(self):
        pytest.importorskip("rank_bm25")

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


# --- Iteration 3 --------------------------------------------------------------

class TestCouleurs:
    def test_bleu_fixe_les_composantes(self):
        r = exp.corriger_couleur("hue.set_group_color_rgb", {"red": 0, "green": 255, "blue": 0}, "mets une ambiance bleue")
        assert (r["red"], r["green"], r["blue"]) == (0, 0, 255)

    def test_cles_courtes_respectees(self):
        r = exp.corriger_couleur("set_color_rgb", {"r": 1, "g": 2, "b": 3}, "mets en rouge")
        assert (r["r"], r["g"], r["b"]) == (255, 0, 0) and "red" not in r

    def test_sans_couleur_nommee_inchange(self):
        args = {"red": 1, "green": 2, "blue": 3}
        assert exp.corriger_couleur("set_color_rgb", args, "change la couleur") == args

    def test_outil_sans_couleur_inchange(self):
        assert exp.corriger_couleur("tv.power_on", {}, "mets la tv en bleu") == {}

    def test_ne_mute_pas_l_entree(self):
        args = {"red": 1}
        exp.corriger_couleur("set_color_rgb", args, "vert")
        assert args == {"red": 1}


class TestExemplesParSpec:
    BRUTES = ["tv.ambilight_on: Active l'Ambilight | Utilise pour: allume l'ambilight. active les LEDs",
              "tv.power_on: Allume la TV",
              "hue.turn_on_light: Turn on | Utilise pour: allumer une lumière. allume la lampe"]

    def test_un_exemple_par_spec_avec_paraphrase(self):
        r = exp.exemples_par_spec(self.BRUTES, ["tv.ambilight_on", "tv.power_on", "hue.turn_on_light"])
        assert 'Requete: "allume l\'ambilight" -> {"tool": "ambilight_on"}' in r
        assert 'Requete: "allumer une lumière" -> {"tool": "turn_on_light"}' in r
        assert "power_on" not in r

    def test_vide_sans_paraphrase(self):
        assert exp.exemples_par_spec(self.BRUTES, ["tv.power_on"]) == ""

    def test_premiere_paraphrase(self):
        assert exp.premiere_paraphrase(self.BRUTES[0]) == "allume l'ambilight"
        assert exp.premiere_paraphrase("x: rien") is None


class TestPoidsRares:
    def test_diffusion_pese_plus_que_le_verbe(self):
        specs = ["denon.volume_down: volume_down()", "catt.cast_volume: cast_volume(level)"]
        # sans poids : volume (+1) pour les deux, diffusion (+1) pour cast_volume -> deja devant
        assert exp.score_mots("catt.cast_volume", "baisse le volume de la diffusion", poids_rares=True) == 3
        assert exp.score_mots("denon.volume_down", "baisse le volume de la diffusion", poids_rares=True) == 1
        assert exp.boost_mots(specs, "baisse le volume de la diffusion", poids_rares=True)[0].startswith("catt.")

    def test_sans_option_comportement_inchange(self):
        assert exp.score_mots("catt.cast_volume", "baisse le volume de la diffusion") == 2


class TestFusionRRFUnRangParListe:
    def _item(self, nom, score, source="capabilities"):
        return {"document": f"doc {nom}", "metadata": {"tool_name": nom}, "score": score, "source": source}

    def test_un_doublon_semantique_ne_cumule_pas(self):
        """a (caps rang 1 + params rang 3) ne doit pas depasser b (rang 2 semantique + rang 1 lexical)."""
        sem = [self._item("a", 0.9), self._item("b", 0.8), self._item("a", 0.7, "parameters")]
        lex = [self._item("b", 0.5, "lexical")]
        r = exp.fusion_rrf(sem, lex)
        assert r[0]["metadata"]["tool_name"] == "b"


# --- Iteration 4 --------------------------------------------------------------

class TestExempleProche:
    BRUTE = ("tv.ambilight_off: Desactive l'Ambilight | Utilise pour: désactiver l'ambilight. "
             "éteindre les LEDs. éteins l'ambilight. coupe l'ambilight Catégorie: tv")

    def test_paraphrases_dedoublonnees_sans_categorie(self):
        assert exp.paraphrases(self.BRUTE) == ["désactiver l'ambilight", "éteindre les LEDs",
                                               "éteins l'ambilight", "coupe l'ambilight"]

    def test_la_plus_proche_de_la_requete_en_premier(self):
        assert exp.paraphrases_proches(self.BRUTE, "eteins l ambilight")[0] == "éteins l'ambilight"

    def test_exemple_proche_dans_le_bloc(self):
        r = exp.exemples_par_spec([self.BRUTE], ["tv.ambilight_off"], requete="eteins l ambilight")
        assert r.splitlines()[1] == 'Requete: "éteins l\'ambilight" -> {"tool": "ambilight_off"}'

    def test_sans_requete_premiere_paraphrase(self):
        r = exp.exemples_par_spec([self.BRUTE], ["tv.ambilight_off"])
        assert "désactiver l'ambilight" in r.splitlines()[1]

    def test_deux_exemples(self):
        r = exp.exemples_par_spec([self.BRUTE], ["tv.ambilight_off"], nb=2)
        assert len(r.strip().splitlines()) == 3


class TestSignature:
    CAP = {"source": "capabilities", "metadata": {"tool_name": "tv.ambilight_mode"},
           "document": "Change le mode Ambilight | Utilise pour: changer le mode ambilight", "score": 0.6}
    PAR = {"source": "parameters", "metadata": {"tool_name": "tv.ambilight_mode"},
           "document": "tv.ambilight_mode: Change le mode. Signature: ambilight_mode(mode: string) Change", "score": 0.4}

    def test_signature_jointe_au_doc_capabilities(self):
        r = exp.joindre_signatures([self.CAP, self.PAR])
        assert r[0]["document"].endswith("Signature: ambilight_mode(mode: string)")
        assert r[1] is self.PAR

    def test_compact_spec_retrouve_le_format_court(self):
        from lyra.models.ephaistos import Ephaistos
        doc = exp.joindre_signatures([self.CAP, self.PAR])[0]["document"]
        assert Ephaistos._compact_spec(f"tv.ambilight_mode: {doc}") == "tv.ambilight_mode: ambilight_mode(mode: string)"

    def test_sans_doc_parameters_inchange(self):
        r = exp.joindre_signatures([self.CAP])
        assert r[0] is self.CAP

    def test_ne_mute_pas_l_entree(self):
        exp.joindre_signatures([self.CAP, self.PAR])
        assert "Signature" not in self.CAP["document"]


class TestConsigneOnOff:
    def test_detecte_les_verbes(self):
        assert exp.verbe_onoff("éteins la télé") and exp.verbe_onoff("allume l ambilight")
        assert not exp.verbe_onoff("monte le volume")


class TestMotsUrl:
    Q = "caste cette video youtube https://youtu.be/dQw4w9WgXcQ"

    def test_url_youtube_detectee(self):
        assert exp.url_youtube(self.Q) and exp.url_youtube("https://www.youtube.com/watch?v=x")
        assert not exp.url_youtube("https://example.org/video.mp4")

    def test_sans_option_cast_url_marque(self):
        assert exp.score_mots("catt.cast_url", self.Q) == 1

    def test_avec_option_cast_url_ne_marque_plus(self):
        assert exp.score_mots("catt.cast_url", self.Q, cibler_youtube=True) == 0
        assert exp.score_mots("catt.cast_youtube", self.Q, cibler_youtube=True) >= 2

    def test_url_generique_inchangee(self):
        assert exp.score_mots("catt.cast_url", "caste https://example.org/a.mp4", cibler_youtube=True) == 1


# --- Jeu hors regles ------------------------------------------------------------

class TestCarteEquipements:
    def test_ampli_designe_denon(self):
        specs = ["tv.volume_up: volume_up()", "denon.volume_up: volume_up()"]
        assert exp.boost_mots(specs, "l'ampli, un cran plus fort", equipements=True)[0].startswith("denon.")

    def test_chromecast_designe_cast(self):
        assert exp.score_mots("catt.cast_stop", "le chromecast, coupe la lecture", equipements=True) >= 1
        assert exp.score_mots("tv.power_off", "le chromecast, coupe la lecture", equipements=True) == 0

    def test_sans_option_inchange(self):
        assert exp.score_mots("denon.volume_up", "l'ampli, un cran plus fort") == 0


class TestMotsRelatifs:
    def test_moins_fort_vise_down_pas_brightness(self):
        specs = ["tv.volume_up: volume_up()", "hue.set_brightness: set_brightness()", "tv.volume_down: volume_down()"]
        assert exp.boost_mots(specs, "un peu moins fort la tele", relatifs=True)[0].startswith("tv.volume_down")
        assert exp.score_mots("hue.set_brightness", "un peu moins fort la tele", relatifs=True) == 0

    def test_plus_fort_vise_up(self):
        assert exp.score_mots("denon.volume_up", "l'ampli, un cran plus fort", relatifs=True) >= 1


class TestExpansion:
    def test_repli_sans_accent_trouve_l_entree_accentuee(self):
        r = exp.etendre_requete("la tele, mets-la en route")
        assert "tv" in r.split() or "télévision" in r  # entree "télé" du dictionnaire

    def test_lexique_ajoute_les_equipements(self):
        sans = exp.etendre_requete("l'ampli en veille")
        avec = exp.etendre_requete("l'ampli en veille", lexique=True)
        assert "denon" not in sans.split() and "denon" in avec.split()

    def test_requete_originale_conservee_en_tete(self):
        assert exp.etendre_requete("coupe sandbox-02", lexique=True).startswith("coupe sandbox-02")

    def test_limite_du_nombre_de_synonymes(self):
        """La limite compte les synonymes (un synonyme peut faire deux mots : "home cinema")."""
        r = exp.etendre_requete("tele leds", lexique=True, max_tokens=2)
        assert len(r.split()) == 2 + 2

    def test_sans_synonyme_inchange(self):
        assert exp.etendre_requete("xyzzy plugh") == "xyzzy plugh"


class TestResolutionParArguments:
    SPECS = ["catt.cast_seek: cast_seek(seconds: integer)", "catt.cast_volume: cast_volume(level: integer)",
             "catt.cast_pause: cast_pause()"]

    def test_nom_invente_resolu_par_les_arguments(self):
        assert exp.resoudre_par_arguments("chromecast", {"command": "seek", "seconds": -10}, self.SPECS,
                                          "recule de dix secondes sur le chromecast") == "catt.cast_seek"

    def test_nom_de_serveur_va_au_rang_1(self):
        assert exp.resoudre_par_arguments("catt", {}, self.SPECS, "y a quoi comme chromecast") == "catt.cast_seek"

    def test_mot_de_la_requete_va_au_rang_1(self):
        assert exp.resoudre_par_arguments("image", {}, ["tv.screen_on: screen_on()", "tv.power_on: power_on()"],
                                          "rends-moi l'image sur la tele") == "tv.screen_on"

    def test_nom_connu_inchange(self):
        assert exp.resoudre_par_arguments("cast_pause", {}, self.SPECS, "x") == "cast_pause"

    def test_inconnu_sans_indice_inchange(self):
        assert exp.resoudre_par_arguments("synchro_lumieres", {}, self.SPECS, "lance la synchro") == "synchro_lumieres"


class TestExempleDescription:
    BRUTE = "tv.screen_on: Rallume l'ecran de la TV apres un screen_off "

    def test_description_sert_d_exemple_sans_paraphrase(self):
        r = exp.exemples_par_spec([self.BRUTE], ["tv.screen_on"], description_si_vide=True)
        assert 'Requete: "Rallume l\'ecran de la TV apres un screen_off" -> {"tool": "screen_on"}' in r

    def test_sans_option_rien(self):
        assert exp.exemples_par_spec([self.BRUTE], ["tv.screen_on"]) == ""


class TestCarteSon:
    def test_couper_le_son_vise_mute(self):
        assert exp.score_mots("denon.mute_on", "coupe le son de l'ampli", son=True) >= 1
        assert exp.score_mots("denon.volume_down", "coupe le son de l'ampli", son=True) == 0

    def test_baisser_le_son_vise_volume(self):
        assert exp.score_mots("denon.volume_down", "baisse le son de l'ampli", son=True) >= 1


class TestSignatureComplete:
    def test_jointure_depuis_la_table(self):
        item = {"source": "capabilities", "metadata": {"tool_name": "hue.set_group_color_rgb"}, "document": "Set color", "score": 0.5}
        r = exp.joindre_signatures_depuis([item], {"hue.set_group_color_rgb": "set_group_color_rgb(red: int, green: int, blue: int)"})
        assert r[0]["document"].endswith("Signature: set_group_color_rgb(red: int, green: int, blue: int)")

    def test_compact_spec_ne_coupe_plus_en_plein_mot(self):
        from lyra.models.ephaistos import Ephaistos
        doc = "hue.set_group_color_rgb: " + "Set color for all lights in a group using RGB values " * 4 + "  Args: group_id: int"
        r = Ephaistos._compact_spec(doc)
        assert "Args" not in r and not r.endswith("gro") and len(r) <= 220


class TestExempleDiscriminant:
    ON = "denon.power_on: Allume | Utilise pour: allumer l'ampli. mettre l'ampli en marche"
    OFF = "denon.power_off: Eteint | Utilise pour: mets l'ampli en veille. éteindre l'ampli"

    def test_mots_communs_a_toutes_les_specs(self):
        assert {"l", "ampli"} <= exp.mots_communs([self.ON, self.OFF])

    def test_la_proximite_ignore_les_mots_communs(self):
        r = exp.exemples_par_spec([self.ON, self.OFF], ["denon.power_on", "denon.power_off"],
                                  requete="mets l'ampli en route", discriminant=True)
        # sans discriminant, "mets l'ampli en veille" serait le plus proche pour power_off ;
        # avec, "mets"/"en" comptent encore pour power_off : on verifie surtout que power_on
        # ne recoit pas un exemple trompeur et que le bloc reste bien forme
        assert '{"tool": "power_on"}' in r and '{"tool": "power_off"}' in r


class TestQuestionEtat:
    def test_question_cible_les_outils_d_etat(self):
        specs = ["denon.power_on: power_on()", "denon.get_status: get_status()"]
        assert exp.boost_mots(specs, "l'ampli est allume ?", etat=True)[0].startswith("denon.get_status")
        assert exp.question_d_etat("la synchro lumiere tourne encore ?")
        assert not exp.question_d_etat("allume la tele")


class TestNomDeVm:
    def test_nom_de_vm_cible_vm(self):
        specs = ["hue.turn_off_group: turn_off_group()", "fedora.vm_stop: vm_stop(vm_name)"]
        assert exp.boost_mots(specs, "coupe sandbox-02", vm=True)[0].startswith("fedora.vm_stop")


class TestVerbesCatt:
    def test_coupe_la_lecture_vise_stop(self):
        specs = ["catt.cast_dual_stop: cast_dual_stop()", "catt.cast_resume: cast_resume()", "catt.cast_stop: cast_stop()"]
        assert exp.boost_mots(specs, "le chromecast, coupe la lecture", catt=True)[0].startswith("catt.cast_stop")

    def test_dual_penalise_sans_contexte(self):
        assert exp.score_mots("catt.cast_dual_stop", "le chromecast, coupe la lecture", catt=True) < \
               exp.score_mots("catt.cast_stop", "le chromecast, coupe la lecture", catt=True)
        assert exp.score_mots("catt.cast_dual_stop", "arrete le dual cast", catt=True) >= 1


class TestArgumentsContradictoires:
    SPECS = ["denon.power_on: power_on()", "denon.volume_set: volume_set(level: integer)", "denon.mute_on: mute_on()"]

    def test_outil_sans_parametre_avec_argument_d_une_autre_spec(self):
        assert exp.basculer_par_arguments("power_on", {"level": 40}, self.SPECS) == "denon.volume_set"

    def test_sans_argument_inchange(self):
        assert exp.basculer_par_arguments("power_on", {}, self.SPECS) == "power_on"

    def test_outil_qui_accepte_l_argument_inchange(self):
        assert exp.basculer_par_arguments("volume_set", {"level": 40}, self.SPECS) == "volume_set"


class TestEntitesEtLangue:
    def test_nom_de_machine_ajoute_vm_avant_le_rag(self):
        r = exp.etendre_requete("coupe sandbox-02", entites=True)
        assert r.startswith("coupe sandbox-02") and "vm" in r.split()

    def test_sans_motif_rien(self):
        assert "vm" not in exp.etendre_requete("coupe le son", entites=True).split()

    def test_lexique_langue_relie_les_mots_orphelins(self):
        r = exp.etendre_requete("je veux un double de preprod-01", langue=True)
        assert "clone" in r.split()
        assert "clone" not in exp.etendre_requete("je veux un double de preprod-01").split()


class TestExemplesDenon:
    def test_bloc_insere_avant_catt_et_garde_par_exemples_cibles(self):
        from lyra.models.ephaistos import EPHAISTOS_SYSTEM_PROMPT as P
        s = exp.inserer_bloc_denon(P)
        assert s.index("=== EXEMPLES DENON") < s.index("=== EXEMPLES CATT")
        c = exp.exemples_cibles(s, {"denon"})
        assert "=== EXEMPLES DENON" in c and "=== EXEMPLES CATT" not in c

    def test_idempotent(self):
        s = exp.inserer_bloc_denon("x === EXEMPLES CATT (Cast video) === y")
        assert exp.inserer_bloc_denon(s) == s


class TestDoublePasse:
    def test_fenetre(self):
        specs = ["a", "b", "c", "d", "e"]
        assert exp.fenetre(specs, 3) == ["a", "b", "c"]
        assert exp.fenetre(specs, 3, skip=3) == ["d", "e"]
        assert exp.fenetre(specs, 0) == specs

    def test_la_seconde_gagne_seulement_si_meilleur_score(self):
        from types import SimpleNamespace as N
        p1 = N(tool="tv.power_on")
        p2 = N(tool="catt.cast_stop")
        assert exp.choisir_par_score(p1, p2, "le chromecast, coupe la lecture") is p2
        assert exp.choisir_par_score(p1, p2, "allume la tele") is p1
        assert exp.choisir_par_score(p1, None, "x") is p1
        assert exp.choisir_par_score(N(tool=None), p2, "x") is p2


class TestNomDeSpec:
    def test_avec_et_sans_prefixe(self):
        assert exp.nom_de_spec("catt.cast_seek: cast_seek(seconds: integer)") == "catt.cast_seek"
        assert exp.nom_de_spec("vm_start(vm_name: string)") == "vm_start"
        assert exp.nom_de_spec("generate_diagram(topic?: string)") == "generate_diagram"

    def test_resolution_ne_deforme_pas_un_nom_connu_sans_prefixe(self):
        """Regression : DEFAUT actif dans les tests d'EPHAISTOS, "generate_diagram" devenait "generate_diagram(topic?"."""
        assert exp.resoudre_par_arguments("generate_diagram", {"topic": "VPN"}, ["generate_diagram(topic?: string)"], "x") == "generate_diagram"
