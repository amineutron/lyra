"""Variantes d'EPHAISTOS et du RAG, choisies par la variable LYRA_EXP.

    LYRA_EXP="exemples_cibles,lexical"   # exactement ces variantes
    LYRA_EXP=""                          # aucune : le comportement d'avant la boucle
    (variable absente)                   # DEFAUT : la configuration retenue par la boucle

Chaque idee est une variante mesurable seule ou combinee, sur le meme code
et la meme graine (scripts/bench_boucle.py). DEFAUT est la configuration
retenue le 2026-09-17 apres cinq iterations : 21/21 sur le banc des modeles
avec qwen2.5-coder:0.5b (5/21 au depart).

Iteration 1 (roadmap-github#72, 2026-09-17) :

- exemples_cibles : le prompt systeme fait ~6 100 tokens dont 44 % de FEDORA ;
  le 0.5b s'ancre sur le premier exemple contenant le verbe de la requete
  ("allume les lumieres" -> turn_on_group, generalise a "allume la tv").
  On n'injecte que les blocs des serveurs presents dans les specs.
  Seule variante gagnante : 5/21 -> 9/21.
- dedup : jusqu'a 40 % des 5 specs remontees sont des doublons. Neutre.
- routage : regle "tel mot-cle -> tel serveur". DEGRADE (4/21).
- index : repondre par le numero de la spec. Annule le gain d'exemples_cibles.
- json_format : ollama contraint la sortie a du JSON. Neutre.

Iteration 2 : le releve de recall a montre que le bon outil n'est dans les
5 specs remontees que pour 8 cas sur 21, et en tete pour 4. Le premier
essai ne montrant qu'une spec, le modele ne peut pas choisir un outil qu'on
ne lui presente pas. Les variantes visent donc le RAG et l'ordre des specs :

- lexical : BM25 sur les documents de capabilities (accents retires), fusion
  RRF avec la recherche semantique. "ambilight", "veille", "chevet" sont des
  mots rares que l'embedding dilue et qu'un index lexical accroche.
- recall8 : 8 candidats au lieu de 5 (6 cas ont le bon outil en rang 5-8).
- carte_mots : boost par TOKENS exacts du nom d'outil (veille -> off,
  chevet -> light, ambiance -> color...). La carte historique compare des
  sous-chaines : "on" est dans "monitor", "light" dans "ambilight".
- top3_direct : 3 specs des le premier essai au lieu d'une seule.
- indice_url : consigne conditionnelle quand la requete contient une URL.

Ecartee avant mesure : retirer les descriptions de serveurs (registre) de la
cascade ne change aucun rang -- elles se classent deja sous les outils.

Iteration 3 (les cinq d'iteration 2 ensemble : 14/21). Les echecs restants
cote modele : "allume l'ambilight" -> tool "allume" (premier mot de la
requete) ; "ambiance bleue" -> bon outil mais (0, 255, 0) ; "baisse le volume
de la diffusion" -> denon.volume_down.

- couleurs : une couleur nommee dans la requete fixe red/green/blue de facon
  deterministe. Un 0.5b n'a pas a calculer une couleur.
- exemple_par_spec : pour chaque spec montree, un exemple tire de sa premiere
  paraphrase ("allume l'ambilight" -> ambilight_on). Le modele voit le verbe
  de la requete associe au bon nom.
- poids_rares : dans carte_mots, un mot-cible rare (ambilight, diffusion,
  chevet) vaut 2 ; "diffusion" doit peser plus que "baisse le volume".
- top5_direct : 5 specs des le premier essai (prime sur top3_direct).

Iteration 4 (exemple_par_spec + poids_rares : 18/21). Les trois echecs ont le
bon outil en rang 1 : "eteins la tele" -> power_on et "eteins l'ambilight" ->
ambilight_on (biais ON/OFF ; l'exemple injecte, premiere paraphrase, ne porte
pas le verbe de la requete) ; "mode lounge" -> bon outil, arguments vides (la
spec montree n'a pas de signature : la fusion garde le doc capabilities).

- exemple_proche : la paraphrase de chaque spec la plus proche de la requete
  (recouvrement de tokens) sert d'exemple ; "eteins l'ambilight" existe mot
  pour mot dans les paraphrases.
- signature : la signature du doc parameters est jointe au doc capabilities ;
  _compact_spec retrouve alors le format d'origine "nom: f(params)".
- consigne_onoff : une ligne "eteins/coupe/desactive = off, allume = on",
  seulement quand la requete contient l'un de ces verbes.
- deux_exemples : deux paraphrases par spec au lieu d'une.

Iteration 5 (exemple_proche + signature : 20/21). Dernier echec : "caste cette
video youtube <url>" -> cast_url, qui perd YouTube Premium (cast_youtube passe
par ADB). La consigne indice_url nomme "url", et "http" donne un point a
cast_url dans carte_mots.

- mots_url : quand l'URL est YouTube, "http" ne cible que "youtube".

Jeu « hors regles » (51 formulations inedites, 2026-09-18) : 13/51 avec la
configuration retenue, le bon outil jamais remonte pour 20 cas. Les mots
d'equipement du langage courant ("ampli", "chromecast", "leds", "synchro")
n'apparaissent ni dans les noms d'outils ni dans les documents.

- carte_equipements : dans carte_mots, ces mots designent le serveur ou la
  famille d'outils (ampli -> denon, chromecast -> cast, leds -> ambilight,
  synchro -> beat, machine -> vm, sauvegardes -> backup).
- mots_relatifs : "moins" -> down/off, "plus" -> up ("un peu moins fort la
  tele" allait a volume_up ; "fort" ne visait que brightness).
- expansion : la requete passee au RAG est enrichie par le SynonymExpander,
  comme en production (le banc appelait cascade_search sur la requete brute),
  avec un repli sans accent : le dictionnaire dit "télé", le STT dit "tele".
- lexique : synonymes d'equipement absents du dictionnaire (ampli -> denon,
  chromecast -> cast, leds -> ambilight, synchro -> beat...), ajoutes a
  l'expansion. Implique expansion.

Iteration 2 hors regles (14/51 : le bon outil est en tete et le modele se
trompe quand meme). Reponses brutes : noms inventes a partir de la requete
("image", "chromecast", "catt", "synchro_lumieres") quand l'outil en tete
n'a pas de paraphrase donc pas d'exemple ; "gro": 1 pour group_id (spec
tronquee a 200 caracteres) ; "coupe le son de l'ampli" -> volume_down.

- exemple_description : sans paraphrase, la description de la spec sert
  d'exemple ("Rallume l'ecran de la TV" -> screen_on).
- signature_complete : la signature est jointe depuis toute la collection
  parameters, pas seulement depuis les resultats remontes.
- resolution_arguments : un nom d'outil inconnu est remplace par la spec
  montree dont la signature contient les arguments renvoyes ("seconds" ->
  cast_seek) ; a defaut, si le nom est un serveur ou un mot de la requete,
  par la spec de rang 1.
- carte_son : "son" cible le volume, sauf avec couper/remettre : le mute.

Iteration 3 hors regles (21/51 ; catt 1/10, denon 3/10). Reponses brutes :
"mets l'ampli en route" copie l'exemple "mets l'ampli en veille -> power_off"
(quatre mots communs, le seul mot discriminant ignore) ; "regle l'ampli a 40"
-> power_on avec level: 40 ; "l'ampli est allume ?" -> power_on ; "coupe
sandbox-02" remonte des outils Hue ; les verbes oraux du cast (fige, remets,
coupe la lecture, a trente pour cent) ne sont dans aucune carte.

- exemple_discriminant : la proximite ignore les mots presents dans toutes
  les paraphrases candidates ("mets", "ampli", "en") ; seuls les mots qui
  departagent comptent.
- question_etat : une question ("... ?", "est-il", "tourne encore") cible
  les outils status/state/info/get.
- nom_de_vm : un motif de nom de VM ("sandbox-02") cible les outils vm.
- verbes_catt : coupe -> stop/off, fige/gele -> pause, remets/reprends ->
  resume, recule -> seek, "a N"/"pour cent" -> set/volume ; les outils
  "dual" ne marquent que si la requete parle de dual/synchro/pc.
- arguments_contradictoires : un outil sans parametre renvoye avec un
  argument qui appartient a une seule autre spec montree bascule vers elle.
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata

VARIANTES = (
    "exemples_cibles", "dedup", "routage", "index", "json_format",
    "lexical", "recall8", "carte_mots", "top3_direct", "indice_url",
    "couleurs", "exemple_par_spec", "poids_rares", "top5_direct",
    "exemple_proche", "signature", "consigne_onoff", "deux_exemples",
    "mots_url",
    "carte_equipements", "mots_relatifs", "expansion", "lexique",
    "exemple_description", "signature_complete", "resolution_arguments", "carte_son",
    "exemple_discriminant", "question_etat", "nom_de_vm", "verbes_catt", "arguments_contradictoires",
)

_BLOC_PAR_SERVEUR = {
    "fedora": "FEDORA",
    "hue": "HUE",
    "tv": "TV",
    "catt": "CATT",
    "mermaid": "MERMAID",
    "screen-manager": "SCREEN-MANAGER",
}

REGLE_ROUTAGE = """ROUTAGE PAR MOT-CLE (prioritaire sur les exemples) :
- tv, tele, television, ambilight, netflix -> un outil tv.*
- lumiere, lampe, ampoule, luminosite, ambiance, couleur -> un outil hue.*
- cast, caste, diffuse, diffusion, chromecast -> un outil catt.*
- vm, machine virtuelle, preprod, sandbox -> un outil fedora.vm_*
- backup, sauvegarde -> un outil fedora.backup_* ; snapshot -> fedora.vm_snapshot
- denon, ampli, amplificateur -> un outil denon.*

"""

CONSIGNE_INDEX = ('\nReponds dans le champ "tool" par le NUMERO de la spec choisie '
                  '(1, 2, 3...), jamais par son nom.')

CONSIGNE_URL = ("\nLa requete contient une URL : choisis l'outil qui accepte une url "
                "(youtube, url), pas un outil de navigateur.")

# Mot de la requete (normalise, sans accent) -> tokens du nom d'outil qu'il
# designe. On ne met que des mots qui nomment une CIBLE ou une PROPRIETE, pas
# les verbes (deja couverts par _FR_ACTION_MAP), ni les mots trop larges
# ("tv", "lumiere") qui apparaissent dans la plupart des requetes.
MOTS_CIBLES: dict[str, tuple[str, ...]] = {
    "ambilight": ("ambilight",),
    "veille": ("off", "standby"),
    "chevet": ("light",),
    "lampe": ("light",),
    "ampoule": ("light",),
    "fort": ("brightness",),
    "fortes": ("brightness",),
    "forte": ("brightness",),
    "faible": ("brightness",),
    "luminosite": ("brightness",),
    "couleur": ("color", "rgb"),
    "ambiance": ("color", "rgb"),
    "rouge": ("color", "rgb"),
    "bleu": ("color", "rgb"),
    "bleue": ("color", "rgb"),
    "vert": ("color", "rgb"),
    "verte": ("color", "rgb"),
    "jaune": ("color", "rgb"),
    "youtube": ("youtube",),
    "http": ("youtube", "url"),
    "https": ("youtube", "url"),
    "diffusion": ("cast",),
    "cast": ("cast",),
    "chromecast": ("cast",),
    "volume": ("volume",),
    "son": ("volume",),
    "secondes": ("seek",),
    "minutes": ("seek",),
    "netflix": ("app",),
    "application": ("app",),
    "appli": ("app",),
}

# Mots du langage courant -> serveur ou famille d'outils (variante carte_equipements)
MOTS_EQUIPEMENTS: dict[str, tuple[str, ...]] = {
    "ampli": ("denon",), "amplificateur": ("denon",), "denon": ("denon",),
    "chromecast": ("cast", "catt"), "cast": ("cast", "catt"),
    "leds": ("ambilight",), "led": ("ambilight",),
    "synchro": ("beat",), "synchronisation": ("beat",),
    "machine": ("vm",), "vm": ("vm",), "serveur": ("vm",),
    "sauvegarde": ("backup",), "sauvegardes": ("backup",), "backup": ("backup",),
    "lampe": ("light",), "lumiere": ("light", "group"), "lumieres": ("group",),
    "scene": ("scene",), "ambiance": ("scene", "color"),
    "telecommande": ("key",), "touche": ("key",),
    "applis": ("apps",), "applications": ("apps",),
    "ecran": ("screen",), "image": ("screen",),
}

# Verbes oraux du cast et reglages (variante verbes_catt)
VERBES_CATT: dict[str, tuple[str, ...]] = {
    "coupe": ("stop", "off"), "couper": ("stop", "off"), "arrete": ("stop",), "stoppe": ("stop",),
    "fige": ("pause",), "gele": ("pause",), "pause": ("pause",),
    "remets": ("resume", "on"), "reprends": ("resume",), "relance": ("resume",), "continue": ("resume",),
    "recule": ("seek",), "avance": ("seek",), "secondes": ("seek",),
    "regle": ("set",), "regler": ("set",), "cent": ("volume", "set"), "pourcent": ("volume", "set"),
}
_MOTS_DUAL = {"dual", "synchro", "synchronise", "synchronisee", "pc", "firefox", "decalage", "resynchronise"}

# Question d'etat -> outils d'information (variante question_etat)
_MARQUES_QUESTION = {"?", "est-il", "est-elle", "tourne", "encore", "quel", "quelle", "quels", "quelles",
                     "combien", "ou", "quoi", "comment", "etat"}
_CIBLES_ETAT = ("status", "state", "info", "get", "list", "scan")

_NOM_DE_VM = re.compile(r"\b[a-z]+-\d{1,3}\b")

# Quantite relative -> direction (variante mots_relatifs)
MOTS_RELATIFS: dict[str, tuple[str, ...]] = {
    "moins": ("down", "off"), "plus": ("up",),
    "baisse": ("down",), "monte": ("up",),
}

_RRF_K = 60

# Configuration retenue par la boucle d'amelioration (iteration 5, 21/21).
# Ecartees, mesurees : dedup et json_format (neutres), routage, index,
# consigne_onoff, deux_exemples, top5_direct (degradent), indice_url (coutait
# le dernier cas), couleurs (sans effet), mots_url (non necessaire).
DEFAUT = ("exemples_cibles", "lexical", "recall8", "carte_mots", "top3_direct",
          "exemple_par_spec", "poids_rares", "exemple_proche", "signature")


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


def dedupliquer(specs_compactes: list[str]) -> list[str]:
    """Une seule spec par nom d'outil, la premiere l'emporte (ordre conserve)."""
    vus: set[str] = set()
    out = []
    for spec in specs_compactes:
        nom = spec.split(":")[0].strip()
        if nom in vus:
            continue
        vus.add(nom)
        out.append(spec)
    return out


def numeroter(specs_compactes: list[str]) -> list[str]:
    return [f"{i}. {spec}" for i, spec in enumerate(specs_compactes, 1)]


def resoudre_index(tool, specs_compactes: list[str]):
    """Un numero de spec devient le nom de l'outil ; tout autre tool est rendu tel quel."""
    if tool is None:
        return None
    m = re.fullmatch(r"\s*(\d+)\s*\.?\s*", str(tool))
    if not m:
        return tool
    i = int(m.group(1))
    if 1 <= i <= len(specs_compactes):
        return specs_compactes[i - 1].split(":")[0].strip()
    return tool


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


_VERBES_MUTE = {"coupe", "couper", "coupez", "remets", "remettre", "remet", "rends", "mute", "sourdine"}


def question_d_etat(requete: str) -> bool:
    r = (requete or "").lower()
    return "?" in r or any(m in set(normaliser(r)) for m in _MARQUES_QUESTION if m != "?")


def score_mots(nom_outil: str, requete: str, poids_rares: bool = False,
               cibler_youtube: bool = False, equipements: bool = False,
               relatifs: bool = False, son: bool = False, catt: bool = False,
               etat: bool = False, vm: bool = False) -> int:
    """Nombre de mots-cibles de la requete qui designent un token du nom.

    Avec poids_rares, un mot de MOTS_RARES compte double. Avec cibler_youtube,
    une URL YouTube ne donne plus de point aux outils "url" generiques. Avec
    equipements et relatifs, les tables MOTS_EQUIPEMENTS et MOTS_RELATIFS
    s'ajoutent (le "moins" de "moins fort" annule la cible brightness de "fort").
    """
    tokens = tokens_outil(nom_outil)
    youtube = cibler_youtube and url_youtube(requete)
    mots = normaliser(requete)
    score = 0
    for mot in mots:
        cibles = MOTS_CIBLES.get(mot)
        if youtube and mot in ("http", "https"):
            cibles = ("youtube",)
        if relatifs and mot in ("fort", "forte", "fortes") and "moins" in mots:
            cibles = None
        if son and mot == "son":
            cibles = ("mute",) if any(v in mots for v in _VERBES_MUTE) else ("volume",)
        if catt and mot in VERBES_CATT:
            cibles = tuple(cibles or ()) + VERBES_CATT[mot]
        if equipements and mot in MOTS_EQUIPEMENTS:
            cibles = tuple(cibles or ()) + MOTS_EQUIPEMENTS[mot]
        if relatifs and mot in MOTS_RELATIFS:
            cibles = tuple(cibles or ()) + MOTS_RELATIFS[mot]
        if cibles and any(c in tokens for c in cibles):
            score += 2 if (poids_rares and mot in MOTS_RARES) else 1
    if catt and "dual" in tokens and not (set(mots) & _MOTS_DUAL):
        score -= 1
    if etat and question_d_etat(requete) and any(c in tokens for c in _CIBLES_ETAT):
        score += 2
    if vm and _NOM_DE_VM.search((requete or "").lower()) and "vm" in tokens:
        score += 2
    return score


def boost_mots(specs_compactes: list[str], requete: str, poids_rares: bool = False,
               cibler_youtube: bool = False, equipements: bool = False,
               relatifs: bool = False, son: bool = False, catt: bool = False,
               etat: bool = False, vm: bool = False) -> list[str]:
    """Re-trie les specs par mots-cibles (tri stable : l'ordre precedent departage)."""
    return sorted(specs_compactes,
                  key=lambda s: score_mots(s.split(":")[0].strip(), requete, poids_rares,
                                           cibler_youtube, equipements, relatifs, son, catt, etat, vm),
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

COULEURS: dict[str, tuple[int, int, int]] = {
    "rouge": (255, 0, 0), "bleu": (0, 0, 255), "bleue": (0, 0, 255),
    "vert": (0, 255, 0), "verte": (0, 255, 0), "jaune": (255, 255, 0),
    "blanc": (255, 255, 255), "blanche": (255, 255, 255), "orange": (255, 165, 0),
    "rose": (255, 105, 180), "violet": (128, 0, 128), "violette": (128, 0, 128),
    "cyan": (0, 255, 255), "turquoise": (64, 224, 208),
}

MOTS_RARES = {"ambilight", "diffusion", "chevet", "veille", "cast", "chromecast",
              "youtube", "netflix", "lounge"}


def couleur_nommee(requete: str):
    for mot in normaliser(requete):
        if mot in COULEURS:
            return COULEURS[mot]
    return None


def corriger_couleur(tool, arguments: dict, requete: str) -> dict:
    """Pour un outil *color_rgb*, la couleur nommee dans la requete fixe les composantes.

    Renvoie un nouveau dict ; les cles existantes (red/green/blue ou r/g/b)
    sont respectees, sinon red/green/blue sont ajoutees.
    """
    arguments = dict(arguments or {})
    if not tool or "color_rgb" not in str(tool):
        return arguments
    rgb = couleur_nommee(requete)
    if rgb is None:
        return arguments
    cles = ("r", "g", "b") if {"r", "g", "b"} & set(arguments) else ("red", "green", "blue")
    return {**arguments, **dict(zip(cles, rgb))}


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


def paraphrases_proches(spec_brute: str, requete: str, ignorer: set[str] | None = None) -> list[str]:
    """Paraphrases triees par recouvrement de tokens avec la requete (tri stable).

    `ignorer` : mots qui ne departagent rien (presents dans toutes les specs
    montrees : "mets", "ampli", "en") -- variante exemple_discriminant.
    """
    mots = set(normaliser(requete)) - (ignorer or set())
    liste = paraphrases(spec_brute)
    return sorted(liste, key=lambda p: -len(mots & set(normaliser(p))))


def mots_communs(specs_brutes: list[str]) -> set[str]:
    """Mots presents dans les paraphrases de TOUTES les specs : ils ne departagent rien."""
    ensembles = []
    for brute in specs_brutes:
        mots = set()
        for ph in paraphrases(brute):
            mots |= set(normaliser(ph))
        if mots:
            ensembles.append(mots)
    return set.intersection(*ensembles) if len(ensembles) > 1 else set()


def description_courte(spec_brute: str):
    """"tv.screen_on: Rallume l'ecran de la TV apres un screen_off" -> "Rallume l'ecran de la TV apres un screen_off"."""
    corps = spec_brute.split(":", 1)[1] if ":" in spec_brute else spec_brute
    corps = re.split(r"\s*\|\s*Utilise pour|\s{2,}Args:|\s+Signature:|\n", corps, 1)[0].strip()
    corps = corps.rstrip(".").strip()
    return corps[:80] if corps else None


def exemples_par_spec(specs_brutes: list[str], noms_montres: list[str], maximum: int = 3,
                      requete: str | None = None, nb: int = 1,
                      description_si_vide: bool = False, discriminant: bool = False) -> str:
    """`nb` exemple(s) par spec montree, tires de ses paraphrases. Vide si aucune.

    Avec `requete`, la paraphrase la plus proche de la requete passe en premier
    (variante exemple_proche) ; sinon c'est la premiere du document.
    """
    par_nom = {}
    for brute in specs_brutes:
        nom = brute.split(":")[0].strip()
        par_nom.setdefault(nom, brute)
    lignes = []
    montrees = [par_nom.get(n, "") for n in noms_montres[:maximum]]
    ignorer = mots_communs(montrees) if (requete and discriminant) else set()
    for nom in noms_montres[:maximum]:
        brute = par_nom.get(nom, "")
        phrases = paraphrases_proches(brute, requete, ignorer) if requete else paraphrases(brute)
        if not phrases and description_si_vide:
            desc = description_courte(brute)
            phrases = [desc] if desc else []
        court = nom.split(".")[-1]
        for phrase in phrases[:max(1, nb)]:
            lignes.append(f'Requete: "{phrase}" -> {{"tool": "{court}"}}')
    if not lignes:
        return ""
    return "EXEMPLES POUR CES SPECS:\n" + "\n".join(lignes) + "\n\n"


# --- Iteration 4 : signature jointe, consigne on/off ------------------------------

_VERBES_OFF = {"eteins", "eteindre", "eteint", "coupe", "couper", "desactive", "desactiver", "arrete"}
_VERBES_ON = {"allume", "allumer", "active", "activer", "enclenche", "demarre"}
CONSIGNE_ONOFF = ("\nRAPPEL : eteindre, couper, desactiver = outil *_off ; "
                  "allumer, activer = outil *_on.")


def verbe_onoff(requete: str) -> bool:
    mots = set(normaliser(requete))
    return bool(mots & (_VERBES_OFF | _VERBES_ON))


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

# Synonymes d'equipement absents de data/synonym_dict.json (variante lexique).
# Des MOTS, jamais des phrases du jeu de test : on complete un lexique, on
# n'apprend pas le banc.
LEXIQUE_EQUIPEMENTS: dict[str, tuple[str, ...]] = {
    "tele": ("tv", "television"), "tv": ("tele", "television"),
    "ampli": ("denon", "amplificateur"), "amplificateur": ("denon", "ampli"),
    "chromecast": ("cast", "diffusion"), "cast": ("chromecast",),
    "leds": ("ambilight", "retroeclairage"), "led": ("ambilight",),
    "synchro": ("hue_beat", "beat", "synchronisation"),
    "machine": ("vm", "machine virtuelle"), "serveur": ("vm",),
    "sauvegardes": ("backup", "backups"), "sauvegarde": ("backup",),
    "restauration": ("snapshot", "restore"),
    "tar": ("archive", "export"), "archive": ("export",),
    "clignoter": ("alert", "identifier"),
    "applis": ("applications", "apps"), "appli": ("application", "app"),
    "teinte": ("couleur", "temperature"),
    "ip": ("status", "adresse"),
    "image": ("ecran",),
}

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


def etendre_requete(requete: str, lexique: bool = False, max_tokens: int = 15) -> str:
    """Requete + synonymes de ses mots (dictionnaire de production, repli sans accent).

    Meme strategie que SynonymExpander.expand (requete originale, puis les
    synonymes, au plus max_tokens), mais la recherche se fait sur les mots
    normalises : "tele" trouve l'entree "télé". Avec lexique, LEXIQUE_EQUIPEMENTS
    s'ajoute au dictionnaire.
    """
    dico = _synonymes_du_dictionnaire()
    ajouts: list[str] = []
    vus: set[str] = set()
    for mot in normaliser(requete):
        candidats = list(dico.get(mot, ()))
        if lexique:
            candidats += list(LEXIQUE_EQUIPEMENTS.get(mot, ()))
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
    noms = [sp.split(":")[0].strip() for sp in specs_compactes]
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
    params = {sp.split(":")[0].strip(): _parametres_de(sp) for sp in specs_compactes}
    propres = next((p for n, p in params.items() if n.split(".")[-1].lower() == court), None)
    if propres is None or propres:
        return tool
    cles = {k.lower() for k in arguments}
    candidats = [n for n, p in params.items() if p and cles <= p and n.split(".")[-1].lower() != court]
    return candidats[0] if len(candidats) == 1 else tool
