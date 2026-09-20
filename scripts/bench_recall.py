#!/usr/bin/env python3
"""Recall mecanique d'un jeu, sans appeler le modele : rang du bon outil et precision du critere net.

    LYRA_SEED=42 .venv/bin/python scripts/bench_recall.py --jeu hors_regles_2 \\
        --configs "DEFAUT;DEFAUT,nombres_tri;DEFAUT,nombres_tri,mots_courants_3" [--detail]

Pour chaque configuration LYRA_EXP, rejoue cascade_search + tri des specs sur
chaque cas du jeu et releve le rang du bon outil (r@1, r@3, r@8, absents) et
la precision du critere "net" (rang 1 impose sans le modele : net ok / net
faux). Vingt secondes par configuration, contre dix minutes pour le banc :
c'est la mesure a faire AVANT le banc (docs/dev/BOUCLE_AMELIORATION.md).
"DEFAUT" dans une configuration vaut la configuration par defaut du depot.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from lyra.models import ephaistos_exp as _exp  # noqa: E402

# Nom de variante -> option de score_mots / score_net
_OPTIONS = {
    "poids_rares": "poids_rares", "mots_url": "cibler_youtube", "carte_equipements": "equipements",
    "mots_relatifs": "relatifs", "carte_son": "son", "verbes_catt": "catt",
    "nom_de_vm": "vm", "cartes_tri": "tri", "cartes_fines": "fines", "verbes_tri": "verbes",
    "verbes_courants": "courants", "mots_courants_2": "courants2", "nombres_tri": "nombres",
    "mots_courants_3": "courants3", "cartes_17": "c17",
}


def options_de(variantes: set[str]) -> dict:
    """Options de tri actives pour un ensemble de variantes."""
    return {opt: (var in variantes) for var, opt in _OPTIONS.items()}


def configurations(texte: str) -> list[tuple[str, ...]]:
    """"DEFAUT;DEFAUT,a;b,c" -> [DEFAUT, DEFAUT+a, (b, c)]."""
    out = []
    for morceau in texte.split(";"):
        noms = [v.strip() for v in morceau.split(",") if v.strip()]
        config: list[str] = []
        for nom in noms:
            config += list(_exp.DEFAUT) if nom == "DEFAUT" else [nom]
        out.append(tuple(dict.fromkeys(config)))
    return out


def rang_du_bon_outil(noms: list[str], attendu: str, equivalents=None):
    """Rang (1-based) du bon outil ou d'un equivalent declare par le banc (EQUIVALENCES)."""
    courts = {attendu.split(".")[-1]} | {e.split(".")[-1] for e in (equivalents or ())}
    for i, nom in enumerate(noms):
        if nom.split(".")[-1] in courts:
            return i + 1
    return None


def resume(releves: list[tuple]) -> dict:
    """[(requete, attendu, rang, net)] -> compteurs r@1 / r@3 / r@8 / absents / net ok / net faux."""
    return {
        "r1": sum(1 for *_, k, _n in releves if k == 1),
        "r3": sum(1 for *_, k, _n in releves if k and k <= 3),
        "r8": sum(1 for *_, k, _n in releves if k and k <= 8),
        "absents": sum(1 for *_, k, _n in releves if k is None),
        "net_ok": sum(1 for *_, k, n in releves if n and k == 1),
        "net_ko": sum(1 for *_, k, n in releves if n and k != 1),
    }


def etiquette(config: tuple[str, ...]) -> str:
    extra = [v for v in config if v not in _exp.DEFAUT]
    if set(_exp.DEFAUT) <= set(config):
        return "DEFAUT+" + "+".join(extra) if extra else "DEFAUT"
    return "+".join(config) or "(aucune)"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--jeu", default="hors_regles_2")
    parser.add_argument("--configs", default="DEFAUT")
    parser.add_argument("--modele", default="qwen2.5-coder:0.5b")
    parser.add_argument("--detail", action="store_true", help="liste les cas hors rang 1 ou net faux")
    args = parser.parse_args()

    import yaml
    from test_campaign_llm import EQUIVALENCES, _config_derivee, cas_du_jeu

    from lyra.core.config import RAGConfig
    from lyra.rag_enhanced import EnhancedPipeline
    from lyra.rag_enhanced.config import RAGEnhancedConfig

    configs = configurations(args.configs)
    os.environ["LYRA_EXP"] = ",".join(sorted(set(v for c in configs for v in c)))   # inventaire charge au demarrage
    chemin = Path(_config_derivee(args.modele, None))
    config = RAGConfig.from_yaml(chemin)
    brut = yaml.safe_load(chemin.read_text()) or {}
    enh = EnhancedPipeline(config=config, enhanced_config=RAGEnhancedConfig.from_dict(brut.get("rag_enhanced", {})),
                           enabled=True, tts_mode=False)
    enh.initialize()
    rag, eph = enh._rag_3tier, enh._pipeline_v2._ephaistos
    cas = cas_du_jeu(args.jeu)

    print(f"{'configuration':50s} r@1  r@3  r@8  abs  net(ok/ko)")
    for cfg in configs:
        os.environ["LYRA_EXP"] = ",".join(cfg)
        actives = set(cfg)
        opts = options_de(actives)
        releves = []
        for _cat, _desc, requete, attendu, *_ in cas:
            res = rag.cascade_search(requete) or []
            specs = [f"{(it.get('metadata') or {}).get('tool_name') or '?'}: {it.get('document', '')}" for it in res]
            comp = eph._boost_spec_order([eph._compact_spec(s) for s in specs], requete)
            if "carte_mots" in actives:
                comp = _exp.boost_mots(comp, requete, **opts)
            rang = rang_du_bon_outil([_exp.nom_de_spec(c) for c in comp], attendu, EQUIVALENCES.get(attendu))
            net = _exp.score_net(comp, requete,
                                 **{**opts, "poids_rares": True, "equipements": True, "relatifs": True, "catt": True})
            releves.append((requete, attendu, rang, net))
        r = resume(releves)
        print(f"{etiquette(cfg):50s} {r['r1']:3d}  {r['r3']:3d}  {r['r8']:3d}  {r['absents']:3d}  {r['net_ok']:3d}/{r['net_ko']}")
        if args.detail:
            for requete, attendu, rang, net in releves:
                if rang != 1 or (net and rang != 1):
                    print(f"    r={rang!s:4} net={int(bool(net))} {attendu:26s} <- {requete[:60]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
