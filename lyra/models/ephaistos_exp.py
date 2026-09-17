"""Variantes experimentales d'EPHAISTOS, activees par la variable LYRA_EXP.

    LYRA_EXP="exemples_cibles,dedup"

La variable vide, rien ne change : le comportement de production est
intact. C'est ce qui permet a la boucle d'amelioration
(scripts/bench_boucle.py) de mesurer chaque idee seule, puis combinee, sur
exactement le meme code, avec la meme graine.

Chaque variante repond a une cause mesuree le 2026-09-17 (roadmap-github#72) :

- exemples_cibles : le prompt systeme fait ~6 100 tokens dont 44 % de FEDORA ;
  le 0.5b s'ancre sur le premier exemple contenant le verbe de la requete
  ("allume les lumieres" -> turn_on_group, generalise a "allume la tv").
  On n'injecte que les blocs des serveurs presents dans les specs.
- dedup : jusqu'a 40 % des 5 specs remontees sont des doublons.
- routage : une regle courte "tel mot-cle -> tel serveur", plus facile a
  suivre pour un petit modele que 60 exemples a generaliser.
- index : repondre par le numero de la spec rend impossible d'inventer un nom
  ("stop_cast" pour "cast_stop").
- json_format : ollama contraint la sortie a du JSON, plus de reponse en prose.
"""

from __future__ import annotations

import os
import re

VARIANTES = ("exemples_cibles", "dedup", "routage", "index", "json_format")

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
