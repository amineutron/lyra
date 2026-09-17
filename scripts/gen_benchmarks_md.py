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
