#!/usr/bin/env python3
"""Boucle d'amelioration : mesure chaque variante seule, puis combinee.

    LYRA_SEED=42 .venv/bin/python scripts/bench_boucle.py --modele qwen2.5-coder:0.5b

Pour chaque configuration de LYRA_EXP (aucune, chaque variante seule, chaque
paire, puis toutes ensemble), rejoue le banc des modeles et releve le score.
Ecrit un JSON d'iteration dans benchmarks/results/ et dit si le seuil est
atteint. Une variante n'est retenue que si elle gagne A SEED FIXE : sans
graine, le meme banc varie de +-1 sur 7, on mesurerait le bruit.
"""

from __future__ import annotations

import argparse
import itertools
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))
sys.path.insert(0, str(REPO / "scripts"))

from bench_common import ecrire_resultat  # noqa: E402

from lyra.models.ephaistos_exp import VARIANTES  # noqa: E402

SEUIL = 0.99


def configurations(rapide: bool, variantes: tuple[str, ...] = VARIANTES,
                   socle: tuple[str, ...] = ()) -> list[tuple[str, ...]]:
    """Socle seul, puis chaque variante, chaque paire et toutes -- au-dessus du socle.

    Le socle est l'acquis des iterations precedentes (ex. exemples_cibles) :
    on mesure ce que chaque nouvelle idee ajoute a ce qui marche deja.
    """
    seules = [socle + (v,) for v in variantes]
    tout = [socle + tuple(variantes)]
    if rapide:
        return [socle] + seules + tout
    paires = [socle + p for p in itertools.combinations(variantes, 2)]
    return [socle] + seules + paires + tout


def mesurer(config: tuple[str, ...], modele: str) -> dict:
    """Un passage du banc avec LYRA_EXP = config. Refuse un banc en panne."""
    from test_campaign_llm import _config_derivee, run_llm_tests

    os.environ["LYRA_EXP"] = ",".join(config)
    chemin = _config_derivee(modele, None)
    t0 = time.time()
    results, categories, score_pondere, pannes = run_llm_tests(chemin)
    duree = time.time() - t0
    if pannes:
        raise RuntimeError(f"{len(pannes)} panne(s) technique(s) avec {config or 'defaut'}")
    total = len(results)
    ok = sum(1 for r in results if r["status"] == "LLM_PASS")
    # Score strict (sans la table d'equivalences du banc) : comparable aux iterations 1 et 2.
    ok_strict = sum(1 for r in results if r.get("strict", r["status"] == "LLM_PASS"))
    par_cat = {}
    for r in results:
        cat = r["cat"].split("/")[0]
        par_cat.setdefault(cat, [0, 0])
        par_cat[cat][1] += 1
        par_cat[cat][0] += r["status"] == "LLM_PASS"
    return {
        "variantes": list(config),
        "reussis": ok,
        "reussis_strict": ok_strict,
        "cas": total,
        "taux": round(ok / total, 4) if total else 0.0,
        "score_pondere": score_pondere,
        "par_categorie": {c: f"{a}/{b}" for c, (a, b) in sorted(par_cat.items())},
        "duree_s": round(duree, 1),
        "echecs": [r["query"] for r in results if r["status"] != "LLM_PASS"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modele", default="qwen2.5-coder:0.5b")
    parser.add_argument("--iteration", type=int, default=1, help="numero de la boucle (pour le nom du fichier)")
    parser.add_argument("--rapide", action="store_true", help="variantes seules + toutes, sans les paires")
    parser.add_argument("--seulement", default=None,
                        help="configs a jouer, separees par ';' (ex: 'dedup;dedup,routage')")
    parser.add_argument("--socle", default="",
                        help="variantes acquises, presentes dans toutes les configs (ex: exemples_cibles)")
    parser.add_argument("--variantes", default=",".join(VARIANTES),
                        help="variantes a combiner au-dessus du socle (defaut : toutes)")
    args = parser.parse_args()

    if not os.environ.get("LYRA_SEED"):
        print("LYRA_SEED absente : les scores ne seraient pas comparables. Abandon.", file=sys.stderr)
        sys.exit(2)

    if args.seulement:
        configs = [tuple(v for v in c.split(",") if v) for c in args.seulement.split(";")]
    else:
        socle = tuple(v for v in args.socle.split(",") if v)
        variantes = tuple(v for v in args.variantes.split(",") if v and v not in socle)
        inconnues = set(socle + variantes) - set(VARIANTES)
        if inconnues:
            print(f"Variantes inconnues : {', '.join(sorted(inconnues))}", file=sys.stderr)
            sys.exit(2)
        configs = configurations(args.rapide, variantes, socle)

    print(f"Boucle {args.iteration} -- modele {args.modele} -- seed {os.environ['LYRA_SEED']} "
          f"-- {len(configs)} configurations\n")
    lignes = []
    for config in configs:
        etiquette = "+".join(config) if config else "(defaut)"
        print(f"  [{etiquette}] ...", end="", flush=True)
        try:
            mesure = mesurer(config, args.modele)
        except Exception as exc:
            print(f" PANNE : {exc}")
            lignes.append({"variantes": list(config), "panne": str(exc)})
            continue
        lignes.append(mesure)
        print(f" {mesure['reussis']}/{mesure['cas']} ({mesure['taux']*100:.0f} %, strict {mesure['reussis_strict']})  {mesure['duree_s']:.0f} s")

    valides = [ligne for ligne in lignes if "panne" not in ligne]
    valides.sort(key=lambda ligne: (-ligne["taux"], ligne["duree_s"]))
    meilleur = valides[0] if valides else None

    print(f"\n{'Configuration':34s} {'Score':>8s} {'Taux':>6s} {'Strict':>6s} {'Duree':>7s}")
    for ligne in valides:
        etiquette = "+".join(ligne["variantes"]) if ligne["variantes"] else "(defaut)"
        print(f"{etiquette:34s} {ligne['reussis']:>4d}/{ligne['cas']:<3d} "
              f"{ligne['taux']*100:>5.0f}% {ligne['reussis_strict']:>6d} {ligne['duree_s']:>6.0f}s")

    chemin = ecrire_resultat("boucle", {
        "iteration": args.iteration,
        "seed": os.environ["LYRA_SEED"],
        "seuil": SEUIL,
        "modele_mesure": args.modele,
        "configurations": lignes,
        "meilleure": meilleur,
        "seuil_atteint": bool(meilleur and meilleur["taux"] >= SEUIL),
    }, suffixe=f"{args.modele.replace(':', '-')}-it{args.iteration}")
    print(f"\nEcrit : {chemin.relative_to(REPO)}")
    if meilleur:
        etat = "ATTEINT" if meilleur["taux"] >= SEUIL else "NON ATTEINT -> nouvelle iteration"
        print(f"Seuil {SEUIL*100:.0f} % : {etat} (meilleur : {meilleur['taux']*100:.0f} %)")


if __name__ == "__main__":
    main()
