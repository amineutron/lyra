#!/usr/bin/env python3
"""Figures SVG de la boucle d'amelioration, lues dans benchmarks/results/ (sans dependance).

    .venv/bin/python scripts/gen_figures_boucle.py   # ecrit docs/articles/figures/*.svg

Deux figures : la progression par jeu (meilleure configuration de chaque
iteration) et la generalisation (jeux scelles, mesure unique, contre les jeux
de developpement). Les nombres viennent des JSON publies, jamais d'une saisie.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RESULTS = REPO / "benchmarks" / "results"
OUT = REPO / "docs" / "articles" / "figures"

JEUX = {"modeles": ("Jeu 1 (21, proche des regles)", "#1f77b4"),
        "hors_regles": ("Jeu 2 (51, inedites)", "#d62728"),
        "hors_regles_2": ("Jeu 3 (100, quotidien)", "#2ca02c")}


def series_boucle() -> dict[str, list[tuple[int, float]]]:
    """jeu -> [(iteration, meilleur taux %)], la derniere mesure d'une iteration l'emporte."""
    par_jeu: dict[str, dict[int, float]] = {}
    for f in sorted(RESULTS.glob("*boucle*.json")):
        d = json.loads(f.read_text())
        confs = [c for c in d.get("configurations", []) if "panne" not in c]
        if not confs or "ancienindex" in f.name:
            continue
        best = max(confs, key=lambda c: c["reussis"])
        par_jeu.setdefault(d.get("jeu", "modeles"), {})[int(d["iteration"])] = 100.0 * best["reussis"] / best["cas"]
    return {j: sorted(v.items()) for j, v in par_jeu.items()}


def mesures_scellees() -> tuple[list[tuple[str, int, int]], dict[str, tuple[int, int]]]:
    """Par jeu scelle : la PREMIERE mesure publiee (unique) et la derniere (apres iteration, si differente)."""
    premiere: dict[str, tuple[int, int]] = {}
    derniere: dict[str, tuple[int, int]] = {}
    for f in sorted(RESULTS.glob("*-exp-horsregles*-modeles.json")):
        d = json.loads(f.read_text())
        jeu = d.get("jeu")
        if jeu not in ("hors_regles_2", "hors_regles_3", "hors_regles_4", "hors_regles_5"):
            continue
        valeur = (int(d["statuts"].get("LLM_PASS", 0)), int(d["cas"]))
        premiere.setdefault(jeu, valeur)
        derniere[jeu] = valeur
    ordre = [j for j in ("hors_regles_2", "hors_regles_3", "hors_regles_4", "hors_regles_5") if j in premiere]
    uniques = [(j, *premiere[j]) for j in ordre]
    finaux = {j: derniere[j] for j in ordre if derniere[j] != premiere[j]}
    return uniques, finaux


def _svg(largeur: int, hauteur: int, corps: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{largeur}" height="{hauteur}" '
            f'viewBox="0 0 {largeur} {hauteur}" font-family="sans-serif" font-size="12">\n'
            f'<rect width="100%" height="100%" fill="white"/>\n{corps}</svg>\n')


def figure_progression(series) -> str:
    L, H, ml, mr, mt, mb = 760, 380, 60, 20, 40, 50
    x_max = max(i for v in series.values() for i, _ in v)
    def X(i): return ml + (L - ml - mr) * (i - 1) / max(1, x_max - 1)
    def Y(t): return mt + (H - mt - mb) * (1 - t / 100.0)
    corps = [f'<text x="{L/2}" y="22" text-anchor="middle" font-size="15" font-weight="bold">'
             'Meilleure configuration par iteration, qwen2.5-coder:0.5b, graine 42</text>']
    for t in range(0, 101, 20):
        corps.append(f'<line x1="{ml}" x2="{L-mr}" y1="{Y(t)}" y2="{Y(t)}" stroke="#ddd"/>'
                     f'<text x="{ml-8}" y="{Y(t)+4}" text-anchor="end">{t} %</text>')
    for i in range(1, x_max + 1):
        corps.append(f'<text x="{X(i)}" y="{H-mb+18}" text-anchor="middle">{i}</text>')
    corps.append(f'<text x="{L/2}" y="{H-8}" text-anchor="middle">iteration</text>')
    corps.append(f'<line x1="{ml}" x2="{L-mr}" y1="{Y(99)}" y2="{Y(99)}" stroke="#888" stroke-dasharray="4 4"/>'
                 f'<text x="{L-mr}" y="{Y(99)-4}" text-anchor="end" fill="#888">seuil 99 %</text>')
    ly = H - mb - 70   # legende en bas a droite, hors des courbes
    for jeu, pts in series.items():
        nom, couleur = JEUX.get(jeu, (jeu, "#333"))
        chemin = " ".join(f"{'M' if k == 0 else 'L'}{X(i):.1f},{Y(t):.1f}" for k, (i, t) in enumerate(pts))
        corps.append(f'<path d="{chemin}" fill="none" stroke="{couleur}" stroke-width="2.5"/>')
        for i, t in pts:
            corps.append(f'<circle cx="{X(i):.1f}" cy="{Y(t):.1f}" r="3.5" fill="{couleur}"/>')
        corps.append(f'<rect x="{L-mr-230}" y="{ly-9}" width="12" height="12" fill="{couleur}"/>'
                     f'<text x="{L-mr-212}" y="{ly+2}">{nom}</text>')
        ly += 18
    return _svg(L, H, "\n".join(corps))


def figure_generalisation(uniques, finaux) -> str:
    """Barres : mesure unique du jeu scelle (gris) contre score final apres iteration (couleur)."""
    L, H, ml, mt, mb = 760, 340, 60, 40, 60
    n = len(uniques)
    larg = (L - ml - 20) / max(1, n)
    def Y(t): return mt + (H - mt - mb) * (1 - t / 100.0)
    corps = [f'<text x="{L/2}" y="22" text-anchor="middle" font-size="15" font-weight="bold">'
             'Ce que vaut un jeu scelle : mesure unique (gris) contre score apres iteration (couleur)</text>']
    for t in range(0, 101, 20):
        corps.append(f'<line x1="{ml}" x2="{L-20}" y1="{Y(t)}" y2="{Y(t)}" stroke="#ddd"/>'
                     f'<text x="{ml-8}" y="{Y(t)+4}" text-anchor="end">{t} %</text>')
    noms = {"hors_regles_2": "Jeu 3 (100)", "hors_regles_3": "Jeu 4 (50)", "hors_regles_4": "Jeu 5 (50)", "hors_regles_5": "Jeu 6 (50)"}
    for k, (jeu, r, c) in enumerate(uniques):
        x0 = ml + k * larg + 20
        w = (larg - 40) / 2
        t = 100.0 * r / c
        corps.append(f'<rect x="{x0}" y="{Y(t)}" width="{w}" height="{Y(0)-Y(t)}" fill="#999"/>'
                     f'<text x="{x0+w/2}" y="{Y(t)-5}" text-anchor="middle">{r}/{c}</text>')
        if jeu in finaux:
            fr, fc = finaux[jeu]
            ft = 100.0 * fr / fc
            corps.append(f'<rect x="{x0+w+4}" y="{Y(ft)}" width="{w}" height="{Y(0)-Y(ft)}" fill="#2ca02c"/>'
                         f'<text x="{x0+w+4+w/2}" y="{Y(ft)-5}" text-anchor="middle">{fr}/{fc}</text>')
        else:
            corps.append(f'<text x="{x0+w+4+w/2}" y="{Y(0)-8}" text-anchor="middle" fill="#666">jamais itere</text>')
        corps.append(f'<text x="{x0+w+2}" y="{H-mb+18}" text-anchor="middle">{noms.get(jeu, jeu)}</text>')
    corps.append(f'<text x="{L/2}" y="{H-12}" text-anchor="middle" fill="#444">'
                 'Le score gris est le seul qui mesure la generalisation ; le vert mesure la boucle.</text>')
    return _svg(L, H, "\n".join(corps))


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    series = series_boucle()
    (OUT / "progression.svg").write_text(figure_progression(series))
    uniques, finaux = mesures_scellees()
    (OUT / "generalisation.svg").write_text(figure_generalisation(uniques, finaux))
    print(f"{len(series)} series, {len(uniques)} jeux scelles -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
