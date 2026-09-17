"""Variantes experimentales d'EPHAISTOS, activees par la variable LYRA_EXP.

    LYRA_EXP="exemples_cibles,lexical"

La variable vide, rien ne change : le comportement de production est
intact. C'est ce qui permet a la boucle d'amelioration
(scripts/bench_boucle.py) de mesurer chaque idee seule, puis combinee, sur
exactement le meme code, avec la meme graine.

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
"""

from __future__ import annotations

import os
import re
import unicodedata

VARIANTES = (
    "exemples_cibles", "dedup", "routage", "index", "json_format",
    "lexical", "recall8", "carte_mots", "top3_direct", "indice_url",
    "couleurs", "exemple_par_spec", "poids_rares", "top5_direct",
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

_RRF_K = 60


def actives() -> set[str]:
    """Variantes demandees par LYRA_EXP ; inconnues ignorees."""
    brut = os.environ.get("LYRA_EXP", "")
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


def score_mots(nom_outil: str, requete: str, poids_rares: bool = False) -> int:
    """Nombre de mots-cibles de la requete qui designent un token du nom.

    Avec poids_rares, un mot de MOTS_RARES compte double.
    """
    tokens = tokens_outil(nom_outil)
    score = 0
    for mot in normaliser(requete):
        cibles = MOTS_CIBLES.get(mot)
        if cibles and any(c in tokens for c in cibles):
            score += 2 if (poids_rares and mot in MOTS_RARES) else 1
    return score


def boost_mots(specs_compactes: list[str], requete: str, poids_rares: bool = False) -> list[str]:
    """Re-trie les specs par mots-cibles (tri stable : l'ordre precedent departage)."""
    return sorted(specs_compactes,
                  key=lambda s: score_mots(s.split(":")[0].strip(), requete, poids_rares),
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
        from rank_bm25 import BM25Okapi

        self._documents = list(documents)
        self._metadonnees = list(metadonnees)
        corpus = [normaliser(f"{md.get('tool_name', '')} ".replace("_", " ").replace(".", " ") + doc)
                  for doc, md in zip(self._documents, self._metadonnees)]
        self._bm25 = BM25Okapi(corpus) if corpus else None

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


def premiere_paraphrase(spec_brute: str):
    """"tv.ambilight_on: Active ... | Utilise pour: allume l'ambilight. active..." -> "allume l'ambilight"."""
    m = re.search(r"Utilise pour:\s*([^.|\n]+)", spec_brute or "")
    if not m:
        return None
    phrase = m.group(1).strip()
    return phrase or None


def exemples_par_spec(specs_brutes: list[str], noms_montres: list[str], maximum: int = 3) -> str:
    """Un exemple par spec montree, tire de sa premiere paraphrase. Vide si aucune."""
    par_nom = {}
    for brute in specs_brutes:
        nom = brute.split(":")[0].strip()
        par_nom.setdefault(nom, brute)
    lignes = []
    for nom in noms_montres[:maximum]:
        phrase = premiere_paraphrase(par_nom.get(nom, ""))
        if phrase:
            court = nom.split(".")[-1]
            lignes.append(f'Requete: "{phrase}" -> {{"tool": "{court}"}}')
    if not lignes:
        return ""
    return "EXEMPLES POUR CES SPECS:\n" + "\n".join(lignes) + "\n\n"
