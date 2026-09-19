#!/usr/bin/env python3
"""Genere BENCHMARKS.md depuis les fichiers de benchmarks/results/.

Le tableau publie ne doit jamais etre ecrit a la main : il est reconstruit
depuis les resultats dates, pour que chaque chiffre pointe vers sa preuve.

Usage: .venv/bin/python scripts/gen_benchmarks_md.py [--check]
       --check : echoue si BENCHMARKS.md n'est pas a jour (utile en revue)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BENCHMARKS = REPO / "benchmarks"
RESULTS = BENCHMARKS / "results"
SORTIE = REPO / "BENCHMARKS.md"

# Les bancs nomment les categories par domaine ; le lecteur raisonne par
# serveur MCP. On traduit une fois ici.
_MCP_PAR_CATEGORIE = {
    "TV": "pylips-mcp",
    "HUE": "hue-mcp",
    "CATT": "catt-mcp",
    "DENON": "denon-mcp",
    "FEDORA": "fedora-agents",
    "BACKUP": "fedora-agents",
    "EDGE": "cas limites",
}

LIBELLES = {
    "oneshot_fast": "One-shot, chemin rapide (regle, sans LLM)",
    "oneshot_full": "One-shot, pipeline complet",
    "repl_ready": "REPL : lancement jusqu'au prompt",
    "repl_first_request": "REPL : premiere requete confirmee",
}


def _charger(mesure: str) -> list[dict]:
    fichiers = sorted(RESULTS.glob(f"*-{mesure}.json"))
    return [json.loads(f.read_text()) | {"_fichier": f.name} for f in fichiers]


def _plus_recent(mesure: str) -> dict | None:
    lot = _charger(mesure)
    return max(lot, key=lambda d: d["date"]) if lot else None


def section_daemon(lignes: list[str]) -> None:
    dernier = _plus_recent("daemon")
    if not dernier:
        return
    baseline_nom = dernier.get("baseline", "")
    avant = {}
    if baseline_nom and (BENCHMARKS / baseline_nom).exists():
        avant = json.loads((BENCHMARKS / baseline_nom).read_text())["mesures_s"]

    lignes += [
        "## Latence du pipeline",
        "",
        f"Mesure du {dernier['date']} sur {dernier['materiel']['gpu'].get('nom', 'CPU')}, "
        f"Python {dernier['versions']['python']}, commit `{dernier['versions']['lyra_commit']}` "
        f"([source](benchmarks/results/{dernier['_fichier']})).",
        "",
        "| Scenario | Avant | Apres | Gain |",
        "|---|---:|---:|---:|",
    ]
    for cle, apres in dernier["mesures_s"].items():
        ref = avant.get(cle)
        gain = f"{ref / apres:.1f}x" if ref and apres else "—"
        ref_txt = f"{ref:.2f} s" if ref else "—"
        lignes += [f"| {LIBELLES.get(cle, cle)} | {ref_txt} | {apres:.2f} s | {gain} |"]
    if baseline_nom:
        lignes += ["", f"Ligne de reference : [`{baseline_nom}`](benchmarks/{baseline_nom}) "
                       "(avant le chantier demon).", ""]


def section_regles(lignes: list[str]) -> None:
    dernier = _plus_recent("regles")
    if not dernier:
        return
    taux = dernier["taux_pass"] * 100
    lignes += [
        "## Detection des commandes (152 requetes, sans LLM)",
        "",
        f"Mesure du {dernier['date']} "
        f"([source](benchmarks/results/{dernier['_fichier']})).",
        "",
        f"**{dernier['statuts'].get('PASS', 0)}/{dernier['cas']} PASS ({taux:.1f} %)** — "
        "le moteur de regles seul, sans appel a un modele : resultat deterministe.",
        "",
        "| Categorie | Cas | PASS |",
        "|---|---:|---:|",
    ]
    for cat, statuts in dernier["par_categorie"].items():
        total = sum(statuts.values())
        lignes += [f"| {cat} | {total} | {statuts.get('PASS', 0)} |"]
    lignes += [""]


def section_tts(lignes: list[str]) -> None:
    dernier = _plus_recent("tts")
    if not dernier:
        return
    lignes += [
        "## Synthese vocale",
        "",
        f"Mesure du {dernier['date']}, moteur {dernier.get('moteur', '?')} "
        f"([source](benchmarks/results/{dernier['_fichier']})).",
        "",
        "| Voix | Phrase courte | Phrase longue | RTF |",
        "|---|---:|---:|---:|",
    ]
    for voix in dernier.get("voix", []):
        court = voix["phrases"]["courte"]["warm_s"]
        long_ = voix["phrases"]["longue"]
        lignes += [f"| {voix['voice']} | {court:.3f} s | {long_['warm_s']:.3f} s | {long_['rtf']:.3f} |"]
    lignes += [""]


def _tableau_modeles(lignes: list[str], par_modele: dict[str, dict], titre: str, note: str) -> None:
    lignes += [
        titre,
        "",
        note,
        "",
        "| Modele EPHAISTOS | Cas | Reussis | Taux | Duree | Variantes | Date |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for nom, mesure in sorted(par_modele.items()):
        statuts = mesure.get("statuts", {})
        reussis = statuts.get("LLM_PASS", 0)
        taux = mesure.get("taux_pass", 0) * 100
        duree = mesure.get("duree_s")
        duree_txt = f"{duree:.0f} s" if duree else "—"
        # Les modeles n'ont pas tous ete mesures avec la meme configuration : le
        # nombre de variantes et la date le disent, plutot que de le laisser croire.
        lignes += [f"| `{nom}` | {mesure['cas']} | {reussis} | {taux:.0f} % | {duree_txt} | "
                   f"{len(mesure.get('variantes', []))} | {mesure['date']} |"]
    # Ventilation par serveur MCP : un score global masque le fait qu'un modele
    # peut etre bon sur un serveur et nul sur un autre.
    noms_modeles = list(sorted(par_modele))
    par_mcp: dict[str, dict[str, tuple]] = {}
    for nom, mesure in par_modele.items():
        for categorie, statuts in mesure.get("par_categorie", {}).items():
            mcp = _MCP_PAR_CATEGORIE.get(categorie, categorie)
            total = sum(statuts.values())
            par_mcp.setdefault(mcp, {})[nom] = (statuts.get("LLM_PASS", 0), total)
    if par_mcp:
        lignes += [
            "",
            "| Serveur | Commandes | " + " | ".join(f"`{n}`" for n in noms_modeles) + " |",
            "|---|---:|" + "---:|" * len(noms_modeles),
        ]
        for mcp, scores in sorted(par_mcp.items()):
            total = next((t for _, t in scores.values()), 0)
            cellules = " | ".join(f"{scores.get(n, (0, 0))[0]}/{total}" for n in noms_modeles)
            lignes += [f"| {mcp} | {total} | {cellules} |"]
    lignes += ["", "Sources : " + ", ".join(
        f"[`{m['_fichier']}`](benchmarks/results/{m['_fichier']})"
        for m in par_modele.values()), ""]


def section_modeles(lignes: list[str]) -> None:
    """Comparaison des modeles sur les requetes que les regles ne couvrent pas.

    Les 152 requetes du banc principal sont toutes absorbees par le moteur de
    regles : aucun modele n'y est sollicite, comparer sur ce jeu donnerait
    quatre fois 100 % en zero seconde. Ce tableau porte donc sur les cas
    RULE_MISS, les seuls ou EPHAISTOS travaille reellement.

    Deux tableaux : la configuration de reference, puis la meme mesure avec les
    variantes LYRA_EXP retenues par la boucle d'amelioration.
    """
    lot = _charger("modeles")
    if not lot:
        return
    # une entree par modele et par jeu de variantes : la mesure la plus recente
    reference: dict[str, dict] = {}
    avec_variantes: dict[str, dict] = {}
    hors_regles: dict[str, dict] = {}
    tenu_a_l_ecart: dict[str, dict] = {}
    for mesure in sorted(lot, key=lambda d: d["date"]):
        nom = mesure.get("modeles_mesures", {}).get("ephaistos", "?")
        if mesure.get("jeu", "modeles") == "hors_regles":
            hors_regles[nom] = mesure
        elif mesure.get("jeu") == "hors_regles_2":
            tenu_a_l_ecart[nom] = mesure
        else:
            (avec_variantes if mesure.get("variantes") else reference)[nom] = mesure

    premier = next(iter((reference or avec_variantes).values()))
    lignes += [
        "## Comparaison des modeles (requetes non couvertes par les regles)",
        "",
        f"{premier['cas']} requetes RULE_MISS passees a EPHAISTOS, "
        f"mesurees le {premier['date']} sur "
        f"{premier['materiel']['gpu'].get('nom', 'CPU')}. "
        "Ce banc ne couvre que pylips-mcp, catt-mcp et hue-mcp ; fedora-agents et "
        "denon-mcp sont mesures par le banc de regles.",
        "",
    ]
    if reference:
        _tableau_modeles(lignes, reference, "### Configuration de reference",
                         "Sans variante : le comportement du depot tel quel.")
    if avec_variantes:
        _tableau_modeles(lignes, avec_variantes, "### Avec les variantes retenues par la boucle",
                         "Configuration du jour indique (colonne Variantes) ; le score accepte les "
                         "equivalences declarees du banc.")
    if hors_regles:
        _tableau_modeles(lignes, hors_regles, "### Jeu « hors regles » (formulations inedites)",
                         "51 formulations inedites sur les 5 serveurs (`tests/cases_hors_regles.py`), "
                         "tenues a l'ecart des regles et des paraphrases indexees. Chaque modele est "
                         "mesure avec la configuration du jour indique (colonne Variantes) : seule la "
                         "ligne la plus recente correspond a la configuration par defaut actuelle. "
                         "Ce jeu a servi a onze iterations : ce n'est plus une mesure de generalisation "
                         "pour la configuration finale (voir benchmarks/README.md).")
    if tenu_a_l_ecart:
        _tableau_modeles(lignes, tenu_a_l_ecart, "### Troisieme jeu, tenu a l'ecart (100 formulations)",
                         "`tests/cases_hors_regles_2.py` : 100 formulations ecrites APRES la boucle, dont 50 "
                         "d'usage quotidien avec les noms reels. Une seule mesure par configuration, jamais "
                         "d'iteration dessus : c'est la mesure de generalisation de la configuration finale. "
                         "Une partie de ces phrases est couverte par une regle juste en usage reel "
                         "(scripts/controle_hors_regles.py --jeu 2 les compte) ; le banc mesure le modele "
                         "sur toutes.")


def section_boucle(lignes: list[str]) -> None:
    """Boucle d'amelioration : une ligne par iteration, la meilleure configuration.

    Les variantes sont inactives par defaut (LYRA_EXP) : ce tableau dit ce
    que chaque iteration a gagne, pas ce que la production fait.
    """
    lot = _charger("boucle")
    if not lot:
        return
    lot.sort(key=lambda d: (d.get("iteration", 0), d["date"]))
    modele = lot[-1].get("modele_mesure", "?")
    lignes += [
        "## Boucle d'amelioration (variantes LYRA_EXP, inactives par defaut)",
        "",
        f"Modele mesure : `{modele}`, graine `{lot[-1].get('seed', '?')}`. "
        "Le score strict ignore la table d'equivalences du banc (comparable entre iterations).",
        "",
        "| Iteration | Configurations | Meilleure configuration | Score | Strict |",
        "|---:|---:|---|---:|---:|",
    ]
    for it in lot:
        meilleure = it.get("meilleure") or {}
        variantes = "+".join(meilleure.get("variantes", [])) or "(defaut)"
        score = f"{meilleure.get('reussis', 0)}/{meilleure.get('cas', 0)}"
        strict = meilleure.get("reussis_strict")
        strict_txt = str(strict) if strict is not None else "="
        lignes += [f"| {it.get('iteration', '?')} | {len(it.get('configurations', []))} | "
                   f"`{variantes}` | {score} | {strict_txt} |"]
    lignes += ["", "Sources : " + ", ".join(
        f"[`{m['_fichier']}`](benchmarks/results/{m['_fichier']})" for m in lot), ""]


def generer() -> str:
    lignes = [
        "# Mesures",
        "",
        "Tableau genere par `scripts/gen_benchmarks_md.py` depuis les resultats de",
        "`benchmarks/results/`. Ne pas editer a la main : relancer `make bench`.",
        "",
        "Protocole, materiel et format : [`benchmarks/README.md`](benchmarks/README.md).",
        "",
    ]
    section_daemon(lignes)
    section_regles(lignes)
    section_modeles(lignes)
    section_boucle(lignes)
    section_tts(lignes)
    if len(lignes) <= 7:
        lignes += ["_Aucun resultat dans `benchmarks/results/`. Lancer `make bench`._", ""]
    return "\n".join(lignes)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="echoue si BENCHMARKS.md n'est pas a jour")
    args = parser.parse_args()

    contenu = generer()
    if args.check:
        actuel = SORTIE.read_text() if SORTIE.exists() else ""
        if actuel != contenu:
            print("BENCHMARKS.md est perime : relancer make bench", file=sys.stderr)
            sys.exit(1)
        print("BENCHMARKS.md est a jour")
        return

    SORTIE.write_text(contenu)
    print(f"Ecrit : {SORTIE.relative_to(REPO)}")


if __name__ == "__main__":
    main()
