"""Mecanisme d'EPHAISTOS et du RAG au-dela du prompt : tri des specs, cartes de
mots, expansion de la requete, resolutions apres la reponse du modele.

Chaque levier est une variante nommee, activable par LYRA_EXP :

    (variable absente)                   # DEFAUT : toutes les variantes retenues
    LYRA_EXP="exemples_cibles,lexical"   # exactement celles-la (ablation, bench)
    LYRA_EXP=""                          # aucune : le comportement d'avant la boucle

Le 2026-09-20, apres 21 iterations, les 17 variantes refutees ou neutres ont
ete retirees du code ; les 42 restantes forment la configuration retenue.
L'histoire de chaque variante, ses mesures et ce qu'elle a appris sont dans
docs/dev/BOUCLE_AMELIORATION.md et dans BENCHMARKS.md (scripts :
bench_boucle.py, bench_recall.py, controle_hors_regles.py).
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata

from .cartes import (  # noqa: F401  (re-exportes : les tests et les scripts lisent exp.MOTS_TRI...)
    _CIBLES_ETAT,
    _COULEURS,
    _MARQUES_QUESTION,
    _MODES_AMBILIGHT,
    _MOTS_COMMANDE,
    _MOTS_DUAL,
    _PIECES,
    _RARES_FINS,
    _VERBES_MUTE,
    CARTES_17,
    EXEMPLES_DENON,
    LEXIQUE_17,
    LEXIQUE_COURANT,
    LEXIQUE_COURANT_2,
    LEXIQUE_COURANT_3,
    LEXIQUE_EQUIPEMENTS,
    LEXIQUE_LANGUE,
    MOTS_CIBLES,
    MOTS_EQUIPEMENTS,
    MOTS_FINS,
    MOTS_RARES,
    MOTS_RELATIFS,
    MOTS_TRI,
    NOMBRES,
    VERBES_CATT,
    VERBES_COURANTS,
    VERBES_COURANTS_2,
    VERBES_COURANTS_3,
    VERBES_TRI,
)

# Les variantes retenues, dans l'ordre ou elles sont entrees dans la configuration.
VARIANTES = (
    "exemples_cibles", "lexical", "recall8", "carte_mots", "top3_direct",
    "exemple_par_spec", "poids_rares", "exemple_proche", "signature",
    "carte_equipements", "mots_relatifs", "expansion", "lexique",
    "resolution_arguments", "signature_complete", "verbes_catt",
    "arguments_contradictoires", "entites_vm", "lexique_langue",
    "exemples_denon", "double_passe", "args_par_regex",
    "spec_description", "outil_force_si_net", "verification_binaire",
    "cartes_tri", "carte_son", "denon_sans_veille", "cartes_fines",
    "mots_url", "verbes_tri",
    "inventaire_vm", "lexique_courant", "verbes_courants",
    "outil_par_machine", "mots_courants_2",
    "nombres_tri", "mots_courants_3",
    "cartes_17", "lumiere_sans_verbe", "nom_de_vm", "force_definitif",
)

_BLOC_PAR_SERVEUR = {
    "fedora": "FEDORA",
    "hue": "HUE",
    "tv": "TV",
    "catt": "CATT",
    "mermaid": "MERMAID",
    "screen-manager": "SCREEN-MANAGER",
    "denon": "DENON",
}



_NOM_DE_VM = re.compile(r"\b[a-z]+-\d{1,3}\b")



_RRF_K = 60

# La configuration par defaut = toutes les variantes retenues (LYRA_EXP absente).
DEFAUT = VARIANTES


def actives() -> set[str]:
    """Variantes actives : LYRA_EXP si definie (meme vide), sinon DEFAUT ; inconnues ignorees."""
    brut = os.environ.get("LYRA_EXP")
    if brut is None:
        return set(DEFAUT)
    return {v.strip() for v in brut.split(",") if v.strip()} & set(VARIANTES)


def serveurs_des_specs(specs_compactes: list[str]) -> set[str]:
    """Prefixes serveur ("fedora", "catt"...) des specs compactes."""
    out = set()
    for spec in specs_compactes:
        nom = spec.split(":")[0].strip()
        if "." in nom:
            out.add(nom.split(".")[0].lower())
    return out


def exemples_cibles(system_prompt: str, serveurs: set[str]) -> str:
    """Ne garde que l'en-tete et les blocs d'exemples des serveurs donnes.

    Sans serveur reconnu, renvoie le prompt complet : mieux vaut trop
    d'exemples que pas d'exemple du tout.
    """
    voulus = {_BLOC_PAR_SERVEUR[s] for s in serveurs if s in _BLOC_PAR_SERVEUR}
    if not voulus:
        return system_prompt
    parts = re.split(r"(=== EXEMPLES [A-Z-]+ .*?===)", system_prompt)
    garde = [parts[0]]
    for i in range(1, len(parts), 2):
        titre = parts[i]
        corps = parts[i + 1] if i + 1 < len(parts) else ""
        nom = titre.split("EXEMPLES ", 1)[1].split(" ", 1)[0]
        if nom in voulus:
            garde.append(titre + corps)
    return "".join(garde)


# --- Iteration 2 : texte, boost par tokens, URL -------------------------------

def normaliser(texte: str) -> list[str]:
    """Tokens minuscules sans accent ni ponctuation ("Éteins l'Ambilight" -> [eteins, l, ambilight])."""
    sans_accent = unicodedata.normalize("NFKD", texte or "")
    sans_accent = "".join(c for c in sans_accent if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]+", sans_accent.lower())


def tokens_outil(nom_outil: str) -> set[str]:
    """"tv.ambilight_on" -> {"tv", "ambilight", "on"}."""
    return set(normaliser(nom_outil.replace("_", " ").replace(".", " ")))


def url_youtube(requete: str) -> bool:
    return bool(re.search(r"https?://(?:www\.)?(?:youtube\.com|youtu\.be)/", requete or ""))


def question_d_etat(requete: str) -> bool:
    r = (requete or "").lower()
    return "?" in r or any(m in set(normaliser(r)) for m in _MARQUES_QUESTION if m != "?")


def score_mots(nom_outil: str, requete: str, poids_rares: bool = False,
               cibler_youtube: bool = False, equipements: bool = False,
               relatifs: bool = False, son: bool = False, catt: bool = False,
               vm: bool = False, tri: bool = False, fines: bool = False,
               verbes: bool = False, courants: bool = False, courants2: bool = False,
               nombres: bool = False, courants3: bool = False, c17: bool = False) -> int:
    """Nombre de mots-cibles de la requete qui designent un token du nom.

    Avec poids_rares, un mot de MOTS_RARES compte double. Avec cibler_youtube,
    une URL YouTube ne donne plus de point aux outils "url" generiques. Avec
    equipements et relatifs, les tables MOTS_EQUIPEMENTS et MOTS_RELATIFS
    s'ajoutent (le "moins" de "moins fort" annule la cible brightness de "fort").
    """
    tokens = tokens_outil(nom_outil)
    youtube = cibler_youtube and url_youtube(requete)
    mots = normaliser(requete)
    if c17:
        # "de la lumiere dans le salon" : le verbe implicite compte dans le tri
        # (sinon "salon" seul pousse le groupe vers set_group_brightness)
        implicite = lumiere_sans_verbe(requete)
        if implicite:
            mots = mots + normaliser(implicite)
    score = 0
    for mot in mots:
        cibles = MOTS_CIBLES.get(mot)
        if youtube and mot in ("http", "https"):
            cibles = ("youtube",)
        if relatifs and mot in ("fort", "forte", "fortes") and "moins" in mots:
            cibles = None
        if son and mot == "son":
            verbes_mute = _VERBES_MUTE | ({"sans"} if c17 else set())   # "sans le son" (cartes_17)
            cibles = ("mute",) if any(v in mots for v in verbes_mute) else ("volume",)
        if tri and mot in MOTS_TRI:
            cibles = tuple(cibles or ()) + MOTS_TRI[mot]
        if courants and mot in VERBES_COURANTS:
            cibles = tuple(cibles or ()) + VERBES_COURANTS[mot]
        if courants2 and mot in VERBES_COURANTS_2:
            cibles = tuple(cibles or ()) + VERBES_COURANTS_2[mot]
        if courants3 and mot in VERBES_COURANTS_3:
            cibles = tuple(cibles or ()) + VERBES_COURANTS_3[mot]
        if nombres and (mot in NOMBRES or mot.isdigit()) and not question_franche(requete):
            cibles = tuple(cibles or ()) + ("set",)
        if c17 and mot in CARTES_17:
            cibles = tuple(cibles or ()) + CARTES_17[mot]
        if c17 and mot == "point" and "restauration" not in mots:
            cibles = tuple(cibles or ()) + ("status",)
        if c17 and mot in ("plus", "moins") and set(mots) & {"froide", "chaude", "froid", "chaud"}:
            cibles = ("temperature",)
        if c17 and mot in _PIECES and not set(mots) & {"ampli", "denon", "amplificateur"}:
            # "la lampe du bureau" : une lampe ; "allume l'entree" : une piece Hue (lampe ou groupe)
            if "lampe" in mots:
                cibles = ("light",)
            elif set(mots) & {"cent", "pourcent"} or any(m.isdigit() or m in NOMBRES for m in mots):
                cibles = ("group",)   # it21 : "le salon a 70 %" regle la piece entiere
            else:
                cibles = ("hue", "group")   # "allume l'entree" : lampe ou groupe, le modele tranche
        if c17 and mot in ("tele", "tv", "television") and \
                (contient_url(requete) or set(mots) & {"chromecast", "cast", "ampli", "denon", "amplificateur", "pc"}):
            cibles = None   # "balance ce lien sur la tele", "l'ampli sur l'entree tele" : la tele n'est pas l'appareil vise
        if fines and mot in MOTS_FINS:
            cibles = tuple(cibles or ()) + MOTS_FINS[mot]
        if fines and mot == "lecture" and any(v in mots for v in VERBES_CATT):
            cibles = None   # "fige la lecture" : le verbe decide, pas "lecture"
        if verbes and mot in VERBES_TRI:
            # "l'ampli est allume ?" n'est pas un ordre : dans une question d'etat,
            # le verbe designe les outils d'information
            cibles = tuple(cibles or ()) + (_CIBLES_ETAT if question_d_etat(requete) else VERBES_TRI[mot])
        if verbes and mot in ("youtube", "netflix", "disney", "plex", "spotify") and "http" not in requete.lower() \
                and any(v in mots for v in ("ouvre", "ouvrir", "lance", "lancer", "mets", "regarder")):
            cibles = ("app", "launch")   # sans URL, "ouvre youtube" est une application a lancer
        if catt and mot in VERBES_CATT:
            cibles = tuple(cibles or ()) + VERBES_CATT[mot]
        if son and mot in ("remets", "remettre", "remet", "rends") and "son" in mots:
            cibles = ("off",)   # "remets le son" = fin du mute : ni resume ni on (exclusif, apres les autres cartes)
        if fines and son and mot in ("coupe", "couper", "coupez") and "son" in mots:
            # "coupe le son" = mute_on chez Denon ; ailleurs le mot "son" cible deja mute,
            # et "on" ferait monter screen_on / power_on (it18)
            cibles = ("on",) if (not c17 or set(mots) & {"ampli", "denon", "amplificateur", "home"}) else None
        if c17 and son and mot == "sans" and "son" in mots:
            cibles = ("mute", "on")   # "sans le son" = couper le son
        if c17 and mot == "cent" and "pour" in mots:
            cibles = ("brightness", "volume", "level")   # "N pour cent" est un niveau, pas un reglage quelconque (apres verbes_catt)
        if c17 and mot in ("tourne", "tournent", "combien", "temps", "regarde") and set(mots) & _MOTS_COMMANDE:
            cibles = None   # "depuis combien de temps ... avec uptime" : la commande decide, pas la question
        if c17 and mot == "allumes":
            cibles = ("on", "start")   # "tu me l'allumes ?"
        if c17 and "scene" in mots and mot in ("lance", "mets", "active", "applique", "passe"):
            cibles = ("activate",)   # "lance la scene detente" : activer une scene, pas en creer une
        if c17 and question_franche(requete) and mot in ("pause", "lecture", "lit", "joue", "diffuse", "allumee", "eteinte", "allume", "eteint"):
            cibles = ("status", "state")   # "le chromecast est en pause ?", "test-vm est allumee ?" : un etat
        if c17 and mot in ("allumee", "eteinte", "allumees", "eteintes") and not question_franche(requete):
            cibles = ("on",) if mot.startswith("allum") else ("off",)
        if equipements and mot in MOTS_EQUIPEMENTS:
            cibles = tuple(cibles or ()) + MOTS_EQUIPEMENTS[mot]
        if relatifs and mot in MOTS_RELATIFS:
            cibles = tuple(cibles or ()) + MOTS_RELATIFS[mot]
        if c17 and mot in ("moins", "plus") and set(mots) & {"lumiere", "lumieres", "lampe", "lampes"} and "peu" in mots:
            cibles = ("brightness",)   # "un peu moins de lumiere" : on tamise, on n'eteint pas (apres mots_relatifs)
        if cibles and any(c in tokens for c in cibles):
            score += 2 if (poids_rares and (mot in MOTS_RARES or (fines and mot in _RARES_FINS))) else 1
    if catt and "dual" in tokens and not (set(mots) & _MOTS_DUAL):
        score -= 1
    if vm and noms_de_machines(requete, inventaire=courants or "inventaire_vm" in actives()) and "vm" in tokens:
        score += 2
    if nombres and question_franche(requete) and any(c in tokens for c in _CIBLES_ETAT + (("verify",) if c17 else ())):
        score += 2
    return score


def boost_mots(specs_compactes: list[str], requete: str, poids_rares: bool = False,
               cibler_youtube: bool = False, equipements: bool = False,
               relatifs: bool = False, son: bool = False, catt: bool = False,
               vm: bool = False, tri: bool = False, fines: bool = False,
               verbes: bool = False, courants: bool = False, courants2: bool = False,
               nombres: bool = False, courants3: bool = False, c17: bool = False) -> list[str]:
    """Re-trie les specs par mots-cibles (tri stable : l'ordre precedent departage)."""
    return sorted(specs_compactes,
                  key=lambda s: score_mots(nom_de_spec(s), requete, poids_rares,
                                           cibler_youtube, equipements, relatifs, son, catt, vm, tri, fines,
                                           verbes, courants, courants2, nombres, courants3, c17),
                  reverse=True)


def contient_url(requete: str) -> bool:
    return bool(re.search(r"https?://\S+", requete or ""))


# --- Iteration 2 : recherche lexicale et fusion ---------------------------------

class RechercheLexicale:
    """BM25 sur les documents d'une collection, tokens normalises.

    Le nom de l'outil est ajoute au document : "tv.ambilight_on" apporte les
    tokens "ambilight" et "on" meme si la description ne les repete pas.
    """

    def __init__(self, documents: list[str], metadonnees: list[dict]):
        self._documents = list(documents)
        self._metadonnees = list(metadonnees)
        self._bm25 = None
        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            # Sans rank_bm25 la recherche reste semantique seule : on le dit
            # une fois plutot que de lever en pleine requete (la variante est
            # active par defaut depuis le 2026-09-17).
            logging.getLogger(__name__).warning(
                "rank_bm25 absent : variante lexical inactive (pip install rank-bm25)")
            return
        corpus = [normaliser(f"{md.get('tool_name', '')} ".replace("_", " ").replace(".", " ") + doc)
                  for doc, md in zip(self._documents, self._metadonnees)]
        self._bm25 = BM25Okapi(corpus) if corpus else None

    @property
    def disponible(self) -> bool:
        return self._bm25 is not None

    def chercher(self, requete: str, top_k: int = 8) -> list[dict]:
        """Resultats au meme format que les collections ({'document','metadata','score','source'})."""
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(normaliser(requete))
        ordre = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        maxi = max(scores) if len(scores) else 0.0
        out = []
        for i in ordre[:top_k]:
            if scores[i] <= 0:
                break
            out.append({
                "document": self._documents[i],
                "metadata": self._metadonnees[i],
                # Score borne a 0.5 : un doc trouve par le seul lexical ne doit
                # pas passer pour une correspondance semantique forte.
                "score": round(0.5 * float(scores[i]) / maxi, 4) if maxi else 0.0,
                "source": "lexical",
            })
        return out


def _cle(item: dict) -> str:
    md = item.get("metadata") or {}
    return md.get("tool_name") or md.get("server_name") or (item.get("document") or "")[:40]


def fusion_rrf(semantique: list[dict], lexical: list[dict], k: int = _RRF_K) -> list[dict]:
    """Reciprocal Rank Fusion : un item par outil, trie par la somme des 1/(k+rang).

    Le score semantique d'origine est conserve (les seuils de confiance du
    pipeline continuent de le lire) ; l'ordre, lui, vient de la fusion.
    """
    entrees: dict[str, dict] = {}
    for liste in (semantique, lexical):
        # Un outil ne compte qu'une fois par liste (son meilleur rang) : la liste
        # semantique contient capabilities ET parameters du meme outil, qui
        # cumulaient deux rangs et passaient devant un outil trouve par le seul
        # lexical (ambilight_off perdu selon l'ordre des egalites de l'index).
        vus_ici: set[str] = set()
        for rang, item in enumerate(liste):
            cle = _cle(item)
            entree = entrees.setdefault(cle, {"item": item, "rrf": 0.0})
            if cle not in vus_ici:
                entree["rrf"] += 1.0 / (k + rang + 1)
                vus_ici.add(cle)
            if item.get("score", 0) > entree["item"].get("score", 0) and item.get("source") != "lexical":
                entree["item"] = item
    ordre = sorted(entrees.values(), key=lambda e: e["rrf"], reverse=True)
    return [dict(e["item"], score_rrf=round(e["rrf"], 5)) for e in ordre]


# --- Iteration 3 : couleurs, exemples par spec, mots rares -----------------------



def paraphrases(spec_brute: str) -> list[str]:
    """Phrases de la section "Utilise pour" (dedoublonnees, ordre conserve)."""
    m = re.search(r"Utilise pour:\s*(.+?)(?:\s*(?:Exemples:|Variantes:|Cat[eé]gorie:|Signature:)|$)",
                  spec_brute or "", re.DOTALL)
    if not m:
        return []
    vues: set[str] = set()
    out = []
    for phrase in re.split(r"[.|\n]", m.group(1)):
        phrase = phrase.strip()
        if phrase and phrase not in vues:
            vues.add(phrase)
            out.append(phrase)
    return out


def premiere_paraphrase(spec_brute: str):
    """"tv.ambilight_on: Active ... | Utilise pour: allume l'ambilight. active..." -> "allume l'ambilight"."""
    liste = paraphrases(spec_brute)
    return liste[0] if liste else None


def paraphrases_proches(spec_brute: str, requete: str) -> list[str]:
    """Paraphrases triees par recouvrement de tokens avec la requete (tri stable)."""
    mots = set(normaliser(requete))
    return sorted(paraphrases(spec_brute), key=lambda p: -len(mots & set(normaliser(p))))


def description_courte(spec_brute: str):
    """"tv.screen_on: Rallume l'ecran de la TV apres un screen_off" -> "Rallume l'ecran de la TV apres un screen_off"."""
    corps = spec_brute.split(":", 1)[1] if ":" in spec_brute else spec_brute
    corps = re.split(r"\s*\|\s*Utilise pour|\s{2,}Args:|\s+Signature:|\n", corps, 1)[0].strip()
    corps = corps.rstrip(".").strip()
    return corps[:80] if corps else None


def exemples_par_spec(specs_brutes: list[str], noms_montres: list[str], maximum: int = 3,
                      requete: str | None = None) -> str:
    """Un exemple par spec montree, tire de ses paraphrases. Vide si aucune.

    Avec `requete`, la paraphrase la plus proche de la requete passe en premier
    (variante exemple_proche) ; sinon c'est la premiere du document.
    """
    par_nom = {}
    for brute in specs_brutes:
        nom = brute.split(":")[0].strip()
        par_nom.setdefault(nom, brute)
    lignes = []
    for nom in noms_montres[:maximum]:
        brute = par_nom.get(nom, "")
        phrases = paraphrases_proches(brute, requete) if requete else paraphrases(brute)
        court = nom.split(".")[-1]
        if phrases:
            lignes.append(f'Requete: "{phrases[0]}" -> {{"tool": "{court}"}}')
    if not lignes:
        return ""
    return "EXEMPLES POUR CES SPECS:\n" + "\n".join(lignes) + "\n\n"


# --- Iteration 4 : signature jointe ------------------------------

def extraire_signature(document: str):
    m = re.search(r"Signature:\s+(\S+\(.*?\))", document or "", re.DOTALL)
    return " ".join(m.group(1).split()) if m else None


def joindre_signatures(items: list[dict]) -> list[dict]:
    """Ajoute "Signature: f(...)" au document capabilities d'un outil dont le doc parameters est present.

    Renvoie une nouvelle liste (les dicts enrichis sont des copies). Sans
    signature, _compact_spec montre un paragraphe de paraphrases ; avec, le
    format d'origine "nom: f(params)" que les exemples du prompt utilisent.
    """
    signatures: dict[str, str] = {}
    for item in items:
        if item.get("source") == "parameters":
            nom = (item.get("metadata") or {}).get("tool_name")
            sig = extraire_signature(item.get("document", ""))
            if nom and sig:
                signatures.setdefault(nom, sig)
    out = []
    for item in items:
        nom = (item.get("metadata") or {}).get("tool_name")
        doc = item.get("document", "")
        if item.get("source") != "parameters" and nom in signatures and "Signature:" not in doc:
            out.append({**item, "document": f"{doc} Signature: {signatures[nom]}"})
        else:
            out.append(item)
    return out


# --- Jeu hors regles : expansion de la requete avant le RAG ------------------------


_MOTIF_VM = re.compile(r"\b[a-z]+-\d{1,3}\b")


_expander = None


def _synonymes_du_dictionnaire():
    """SynonymExpander de production, charge une fois ; dict normalise -> synonymes."""
    global _expander
    if _expander is None:
        try:
            from lyra.rag_enhanced.synonym_expander import SynonymExpander
            exp = SynonymExpander()
            brut = getattr(exp, "synonym_dict", {}) or {}
        except Exception:
            brut = {}
        _expander = {" ".join(normaliser(k)): tuple(v) for k, v in brut.items()
                     if isinstance(v, list) and not k.startswith("_")}
    return _expander


def inserer_bloc_denon(system_prompt: str, sans_veille: bool = False) -> str:
    """Ajoute le bloc d'exemples Denon avant le bloc CATT (ou a la fin).

    sans_veille : l'exemple power_off dit "eteins l'ampli" ; "mets l'ampli en
    veille" attirait "mets l'ampli en route" par sa forme (variante denon_sans_veille).
    """
    if "=== EXEMPLES DENON" in system_prompt:
        return system_prompt
    bloc = EXEMPLES_DENON.replace("__VEILLE__", "eteins l'ampli" if sans_veille else "mets l'ampli en veille")
    marque = "=== EXEMPLES CATT"
    if marque in system_prompt:
        return system_prompt.replace(marque, bloc + marque, 1)
    return system_prompt + "\n" + bloc


def etendre_requete(requete: str, lexique: bool = False, max_tokens: int = 15,
                    entites: bool = False, langue: bool = False,
                    inventaire: bool = False, courant: bool = False, courant2: bool = False,
                    courant3: bool = False, lumiere: bool = False, c17: bool = False) -> str:
    """Requete + synonymes de ses mots (dictionnaire de production, repli sans accent).

    Meme strategie que SynonymExpander.expand (requete originale, puis les
    synonymes, au plus max_tokens), mais la recherche se fait sur les mots
    normalises : "tele" trouve l'entree "télé". Avec lexique, LEXIQUE_EQUIPEMENTS
    s'ajoute au dictionnaire.
    """
    dico = _synonymes_du_dictionnaire()
    ajouts: list[str] = []
    vus: set[str] = set()
    if (entites or inventaire) and noms_de_machines(requete, inventaire=inventaire):
        ajouts += ["vm", "machine virtuelle"]
        vus |= {"vm", "machine virtuelle"}
    if c17 and url_youtube(requete):
        ajouts += ["youtube", "video"]   # "passe-moi ca sur le chromecast <url youtube>" : aucun mot ne le disait
        vus |= {"youtube", "video"}
    if lumiere:
        verbe = lumiere_sans_verbe(requete)
        if verbe:
            ajouts.append(verbe)
            vus.add(verbe)
    for mot in normaliser(requete):
        candidats = list(dico.get(mot, ()))
        if lexique:
            candidats += list(LEXIQUE_EQUIPEMENTS.get(mot, ()))
        if langue:
            candidats += list(LEXIQUE_LANGUE.get(mot, ()))
        if courant:
            candidats += list(LEXIQUE_COURANT.get(mot, ()))
        if courant2:
            candidats += list(LEXIQUE_COURANT_2.get(mot, ()))
        if courant3:
            candidats += list(LEXIQUE_COURANT_3.get(mot, ()))
        if c17:
            candidats += list(LEXIQUE_17.get(mot, ()))
        for syn in candidats:
            cle = " ".join(normaliser(syn))
            if cle and cle not in vus and cle not in normaliser(requete):
                vus.add(cle)
                ajouts.append(syn)
            if len(ajouts) >= max_tokens:
                break
        if len(ajouts) >= max_tokens:
            break
    return f"{requete} {' '.join(ajouts)}" if ajouts else requete


# --- Iteration 2 hors regles : resolution par arguments, signatures completes ----

def nom_de_spec(spec_compacte: str) -> str:
    """"catt.cast_seek: cast_seek(seconds: integer)" -> "catt.cast_seek" ; "vm_start(vm_name: string)" -> "vm_start".

    Le premier ":" peut etre celui d'un type quand la spec n'a pas de prefixe
    "nom:" (specs passees telles quelles par les tests et par certains appels).
    """
    return re.split(r"[:(]", spec_compacte or "", 1)[0].strip()


def _parametres_de(spec_compacte: str) -> set[str]:
    """"catt.cast_seek: cast_seek(seconds: integer)" -> {"seconds"}."""
    m = re.search(r"\(([^)]*)\)", spec_compacte)
    if not m:
        return set()
    return {p.strip().split(":")[0].strip().rstrip("?") for p in m.group(1).split(",") if p.strip()}


def resoudre_par_arguments(tool, arguments: dict, specs_compactes: list[str], requete: str):
    """Un nom d'outil qui n'est celui d'aucune spec montree est remplace :

    1. par la spec dont la signature contient le plus d'arguments renvoyes
       ("seconds": -10 -> cast_seek), si une seule l'emporte ;
    2. sinon, si le nom est un prefixe serveur ou un mot de la requete
       ("catt", "chromecast", "image"), par la spec de rang 1.
    Un nom connu est rendu tel quel.
    """
    if not tool or not specs_compactes:
        return tool
    noms = [nom_de_spec(sp) for sp in specs_compactes]
    court = str(tool).split(".")[-1].lower()
    if any(n.lower() == str(tool).lower() or n.split(".")[-1].lower() == court for n in noms):
        return tool
    if arguments:
        cles = {k.lower() for k in arguments}
        scores = [len(cles & _parametres_de(sp)) for sp in specs_compactes]
        meilleur = max(scores)
        if meilleur > 0 and scores.count(meilleur) == 1:
            return noms[scores.index(meilleur)]
    serveurs = {n.split(".")[0].lower() for n in noms if "." in n}
    if court in serveurs or court in set(normaliser(requete)):
        return noms[0]
    return tool


def signatures_completes(collection) -> dict[str, str]:
    """tool_name -> signature, lue une fois dans toute la collection parameters."""
    try:
        tout = collection.get(include=["documents", "metadatas"])
    except Exception:
        return {}
    out: dict[str, str] = {}
    for doc, md in zip(tout.get("documents") or [], tout.get("metadatas") or []):
        nom = (md or {}).get("tool_name")
        sig = extraire_signature(doc or "")
        if nom and sig:
            out.setdefault(nom, sig)
    return out


def joindre_signatures_depuis(items: list[dict], signatures: dict[str, str]) -> list[dict]:
    """Comme joindre_signatures, mais avec une table complete (variante signature_complete)."""
    out = []
    for item in items:
        nom = (item.get("metadata") or {}).get("tool_name")
        doc = item.get("document", "")
        if item.get("source") != "parameters" and nom in signatures and "Signature:" not in doc:
            out.append({**item, "document": f"{doc} Signature: {signatures[nom]}"})
        else:
            out.append(item)
    return out


def basculer_par_arguments(tool, arguments: dict, specs_compactes: list[str]):
    """Outil sans parametre rendu avec un argument qui n'appartient qu'a une autre spec montree.

    "regle l'ampli a 40" -> power_on avec level: 40 : level est le parametre de
    volume_set, et de lui seul -> volume_set. Sans argument, ou si l'outil
    accepte l'argument, rien ne change.
    """
    if not tool or not arguments or not specs_compactes:
        return tool
    court = str(tool).split(".")[-1].lower()
    params = {nom_de_spec(sp): _parametres_de(sp) for sp in specs_compactes}
    propres = next((p for n, p in params.items() if n.split(".")[-1].lower() == court), None)
    if propres is None or propres:
        return tool
    cles = {k.lower() for k in arguments}
    candidats = [n for n, p in params.items() if p and cles <= p and n.split(".")[-1].lower() != court]
    return candidats[0] if len(candidats) == 1 else tool


def fenetre(specs_compactes: list[str], max_specs: int, skip: int = 0) -> list[str]:
    """Les specs montrees : `max_specs` a partir de `skip` (0 = toutes)."""
    if max_specs <= 0:
        return list(specs_compactes[skip:]) if skip else list(specs_compactes)
    return list(specs_compactes[skip:skip + max_specs])


def choisir_par_score(premiere, seconde, requete: str):
    """double_passe : la reponse dont l'outil a le meilleur score de mots l'emporte, la premiere a egalite."""
    if seconde is None or not getattr(seconde, "tool", None):
        return premiere
    if not getattr(premiere, "tool", None):
        return seconde
    def score(a):
        return score_mots(str(a.tool), requete, poids_rares=True, equipements=True, relatifs=True, catt=True)
    return seconde if score(seconde) > score(premiere) else premiere


# --- Iteration 6 hors regles ---------------------------------------------------------

def score_net(specs_compactes: list[str], requete: str, seuil: int = 2, **options) -> bool:
    """Vrai si la spec de rang 1 a un score de mots >= seuil et strictement superieur au rang 2."""
    if not specs_compactes:
        return False
    s1 = score_mots(nom_de_spec(specs_compactes[0]), requete, **options)
    s2 = score_mots(nom_de_spec(specs_compactes[1]), requete, **options) if len(specs_compactes) > 1 else 0
    return s1 >= seuil and s1 > s2


def completer_arguments(tool, arguments: dict, specs_compactes: list[str], requete: str,
                        inventaire: bool = False) -> dict:
    """Arguments deductibles de la requete quand la signature les attend (variante args_par_regex).

    vm_name / source_vm : le premier nom de machine ("sandbox-02") ; new_vm_name :
    le second ; command : le segment apres "avec" (ou ":"). Ne remplace jamais
    une valeur deja presente.
    """
    arguments = dict(arguments or {})
    if not tool:
        return arguments
    court = str(tool).split(".")[-1].lower()
    params = next((_parametres_de(sp) for sp in specs_compactes if nom_de_spec(sp).split(".")[-1].lower() == court), set())
    machines = noms_de_machines(requete, inventaire=inventaire)
    if machines:
        for cle in ("vm_name", "source_vm"):
            if cle in params and not arguments.get(cle):
                arguments[cle] = machines[0]
        if "new_vm_name" in params and not arguments.get("new_vm_name"):
            if len(machines) > 1:
                arguments["new_vm_name"] = machines[1]
            elif inventaire and nouveau_nom(requete, machines[0]):
                arguments["new_vm_name"] = nouveau_nom(requete, machines[0])
    if "command" in params and not arguments.get("command"):
        m = re.search(r"\b(?:avec|via|commande)\s+(.+)$|:\s*(.+)$", requete or "")
        if m:
            arguments["command"] = (m.group(1) or m.group(2)).strip()
    if "mode" in params and not arguments.get("mode"):
        m = re.search(r"\bmode\s+([a-z_]+)", (requete or "").lower())
        if m:
            arguments["mode"] = _MODES_AMBILIGHT.get(m.group(1), m.group(1))
    return arguments




# --- Iteration 7 hors regles ---------------------------------------------------------

def avec_description(spec_compacte: str, spec_brute: str, maximum: int = 70) -> str:
    """"catt.cast_info: cast_info()" + description courte -> "catt.cast_info: cast_info() -- infos ..."."""
    if " -- " in spec_compacte:
        return spec_compacte
    desc = description_courte(spec_brute)
    if not desc:
        return spec_compacte
    desc = desc[:maximum].rstrip()
    return f"{spec_compacte} -- {desc}"


# --- Leviers generiques (2026-09-19, apres le troisieme jeu) --------------------------

_INVENTAIRE_VM: tuple[str, ...] = ()


def definir_inventaire_vm(noms) -> None:
    """Enregistre les noms de machines reels (vm_status au demarrage du pipeline)."""
    global _INVENTAIRE_VM
    _INVENTAIRE_VM = tuple(sorted({str(n).strip().lower() for n in (noms or ()) if str(n).strip()},
                                  key=len, reverse=True))


def inventaire_vm() -> tuple[str, ...]:
    """Noms enregistres, sinon LYRA_VMS ("fedora-base,test-vm"), sinon rien."""
    if _INVENTAIRE_VM:
        return _INVENTAIRE_VM
    brut = os.environ.get("LYRA_VMS", "")
    return tuple(sorted({n.strip().lower() for n in brut.split(",") if n.strip()}, key=len, reverse=True))


def noms_de_machines(requete: str, inventaire: bool = False) -> list[str]:
    """Noms de machines cites, dans l'ordre : inventaire reel (si demande) puis motif "nom-NN"."""
    texte = (requete or "").lower()
    trouves: list[tuple[int, str]] = []
    if inventaire:
        for nom in inventaire_vm():
            for m in re.finditer(rf"(?<![a-z0-9-]){re.escape(nom)}(?![a-z0-9-])", texte):
                trouves.append((m.start(), nom))
    for m in _MOTIF_VM.finditer(texte):
        trouves.append((m.start(), m.group(0)))
    noms = [nom for _, nom in sorted(trouves)]
    # "windows-11" (motif) est un morceau de "windows-11-test" (inventaire) : le plus long gagne
    resultat: list[str] = []
    for nom in noms:
        if nom not in resultat and not any(nom != autre and nom in autre for autre in noms):
            resultat.append(nom)
    return resultat


_NOUVEAU_NOM = re.compile(r"\b(?:en|vers|nomme|nommee|appelle|appelee|appelant|nom)\s+([a-z0-9]+(?:-[a-z0-9]+)+)\b")


def nouveau_nom(requete: str, source: str) -> str | None:
    """"clone fedora-base en fedora-test" -> "fedora-test" (un nom avec tiret apres en/nomme/appelle)."""
    for m in _NOUVEAU_NOM.finditer((requete or "").lower()):
        if m.group(1) != source:
            return m.group(1)
    return None


# --- Iteration 15 ------------------------------------------------------------------

def outil_par_machine(tool, arguments: dict, specs_compactes: list[str], requete: str):
    """"fedora_base" renvoye comme outil pour "reveille fedora-base" -> spec de rang 1, vm_name = fedora-base.

    Le 0.5b copie l'entite en nom d'outil quand le verbe ne lui dit rien. Ne
    touche pas a un nom qui est celui d'une spec montree.
    """
    if not tool or not specs_compactes:
        return tool, arguments
    court = str(tool).split(".")[-1].lower().replace("_", "-")
    noms = [nom_de_spec(sp) for sp in specs_compactes]
    if any(n.split(".")[-1].lower() == str(tool).split(".")[-1].lower() for n in noms):
        return tool, arguments
    machines = noms_de_machines(requete, inventaire=True)
    if court not in machines:
        return tool, arguments
    nouveau = noms[0]
    args = dict(arguments or {})
    params = _parametres_de(specs_compactes[0])
    for cle in ("vm_name", "source_vm"):
        if cle in params and not args.get(cle):
            args[cle] = court
            break
    return nouveau, args


# --- Iteration 16 ------------------------------------------------------------------

_POLITESSE = re.compile(r"\b(?:tu peux|peux-tu|pourrais-tu|tu pourrais|tu veux bien|veux-tu|s'il te plait|stp"
                        r"|tu me |tu nous |tu la |tu le |tu les |tu l'|tu l )")


def question_franche(requete: str) -> bool:
    """Une vraie question d'etat : "?" final ou "est-ce que", sans formule de politesse
    ("tu peux me mettre la tele ?" est un ordre ; "regarde ... avec uptime" aussi)."""
    r = (requete or "").lower().strip()
    if _POLITESSE.search(r):
        return False
    return r.endswith("?") or r.startswith("est-ce que") or r.startswith("est ce que")




# --- Iteration 17 ------------------------------------------------------------------


_VERBES_CONNUS = re.compile(r"\b(?:allume|allumer|eteins|eteindre|eteint|coupe|couper|mets|mettre|baisse|monte|tamise|"
                            r"active|desactive|regle|passe|change|remets|rallume|lance|vire|enleve|met)\b")


def lumiere_sans_verbe(requete: str) -> str | None:
    """"de la lumiere dans le salon" -> "allumer" ; "plus de lumiere au salon" -> "eteindre" ; sinon None.

    Uniquement quand la phrase parle de lumiere sans aucun verbe connu : c'est
    l'article ("de la", "plus de") qui porte l'action.
    """
    mots = normaliser(requete)
    if not ({"lumiere", "lumieres", "lampe", "lampes"} & set(mots)) or _VERBES_CONNUS.search(" ".join(mots)):
        return None
    if "peu" in mots:
        return None   # "un peu plus de lumiere" est un reglage, pas un allumage
    texte = " ".join(mots)
    # Les deux formes : l'index lexical compare des tokens exacts ("allume" dans
    # les paraphrases, "allumer" dans le dictionnaire de synonymes)
    if re.search(r"\bplus (?:de|d) (?:lumiere|lampe)", texte) or "plus" in mots and "moins" not in mots and "fort" not in mots:
        return "eteins eteindre"
    if re.search(r"\b(?:de la|un peu de|de l) lumiere", texte):
        return "allume allumer"
    return None


# --- Inventaire Hue (recette 2026-09-23) --------------------------------------------

_INVENTAIRE_HUE: dict[str, str] = {}


def definir_inventaire_hue(groupes) -> None:
    """Enregistre les groupes Hue reels {id: nom} (hue.get_all_groups au demarrage)."""
    global _INVENTAIRE_HUE
    _INVENTAIRE_HUE = {str(k): str(v) for k, v in dict(groupes or {}).items()}


def inventaire_hue() -> dict[str, str]:
    return dict(_INVENTAIRE_HUE)


def corriger_groupe_hue(tool, arguments: dict, defaut: str = "81") -> dict:
    """Un group_id qui n'existe pas sur le pont est remplace par le groupe par defaut.

    "de la lumiere dans le salon" -> turn_on_group(group_id=1) : le 0.5b invente
    un identifiant, le pont repond "Error executing tool". Sans inventaire, rien
    n'est change.
    """
    if not tool or not _INVENTAIRE_HUE or "group" not in str(tool).split(".")[-1]:
        return arguments
    arguments = dict(arguments or {})
    gid = arguments.get("group_id")
    if gid is not None and str(gid) in _INVENTAIRE_HUE:
        return arguments
    choix = defaut if defaut in _INVENTAIRE_HUE else next(iter(_INVENTAIRE_HUE))
    arguments["group_id"] = int(choix) if choix.isdigit() else choix
    return arguments


def filtrer_missing_args(tool, missing_args, specs_compactes: list[str]) -> list:
    """Ne garde que les arguments manquants qui existent dans la signature de l'outil.

    "le chromecast a fond" -> cast_scan avec missing_args=["chromecast"] : le
    0.5b invente un nom, et le pipeline posait une question sans objet
    (recette 2026-09-23). Sans spec de l'outil, la liste est rendue telle quelle.
    """
    if not tool or not missing_args or not specs_compactes:
        return list(missing_args or [])
    court = str(tool).split(".")[-1].lower()
    params = next((_parametres_de(sp) for sp in specs_compactes
                   if nom_de_spec(sp).split(".")[-1].lower() == court), None)
    if params is None:
        return list(missing_args)
    return [a for a in missing_args if str(a) in params]
