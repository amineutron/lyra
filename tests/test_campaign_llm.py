#!/usr/bin/env python3
"""
Campagne de tests MCP - Phase 2 : test des RULE_MISS via EPHAISTOS (LLM reel)
==============================================================================
Teste les requetes qui ne sont pas couvertes par _rule_based_detect
en les passant directement au pipeline RAG + EPHAISTOS.

Statuts:
  LLM_PASS    : EPHAISTOS identifie le bon outil + args obligatoires corrects
  LLM_PARTIAL : EPHAISTOS identifie le bon outil + args optionnels manquants
  LLM_FAIL    : EPHAISTOS retourne le mauvais outil ou args obligatoires absents

Usage:
  python3 tests/test_campaign_llm.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lyra.core.config import RAGConfig
from lyra.core.pipeline import _resoudre_nom_outil

# ============================================================
# Cas de test: les RULE_MISS attendus (TV, HUE complexe, CATT)
# Format: (categorie, description, query, expected_tool, mandatory_args, optional_args)
# ============================================================

TESTS_LLM = [

    # ================================================================
    # TV - power
    # ================================================================
    ("TV/power", "allume TV",
     "allume la tv",
     "tv.power_on", {}, {}),

    ("TV/power", "eteins TV",
     "eteins la tele",
     "tv.power_off", {}, {}),

    ("TV/power", "TV en veille",
     "mets la tv en veille",
     "tv.power_off", {}, {}),

    # ================================================================
    # TV - apps
    # ================================================================
    ("TV/apps", "lance Netflix",
     "lance netflix sur la tv",
     "tv.launch_app", {}, {}),

    ("TV/apps", "ouvre YouTube",
     "ouvre youtube sur la tele",
     "tv.launch_app", {}, {}),

    ("TV/apps", "video YouTube",
     "joue cette video youtube sur la tv https://youtu.be/dQw4w9WgXcQ",
     "tv.youtube_video", {}, {}),

    # ================================================================
    # TV - ambilight
    # ================================================================
    ("TV/ambilight", "allume ambilight",
     "allume l ambilight",
     "tv.ambilight_on", {}, {}),

    ("TV/ambilight", "eteins ambilight",
     "eteins l ambilight",
     "tv.ambilight_off", {}, {}),

    # "mets l ambilight en bleu" attendait tv.ambilight_set_color, qui n'existe
    # pas dans pylips-mcp (ambilight_on/off/mode seulement) : cas irrealisable,
    # remplace le 2026-09-17 par le seul reglage d'ambilight disponible.
    ("TV/ambilight", "mode ambilight",
     "passe l ambilight en mode lounge",
     "tv.ambilight_mode", {}, {"mode": "lounge_light"}),

    # ================================================================
    # HUE - lumiere individuelle
    # ================================================================
    ("HUE/light", "allume lumiere chevet",
     "allume la lumiere chevet",
     "hue.turn_on_light", {}, {}),

    # ================================================================
    # HUE - brightness / color
    # ================================================================
    ("HUE/brightness", "luminosite 50",
     "mets la luminosite a 50 pour cent",
     "hue.set_brightness", {}, {}),

    ("HUE/brightness", "lumieres plus fortes",
     "mets les lumieres plus fortes",
     "hue.set_brightness", {}, {}),

    ("HUE/color", "couleur rouge",
     "mets les lumieres en rouge",
     "hue.set_color_rgb", {}, {}),

    ("HUE/color", "ambiance bleue",
     "mets une ambiance bleue",
     "hue.set_color_rgb", {}, {}),

    # ================================================================
    # CATT - cast_youtube
    # ================================================================
    ("CATT/youtube", "caste video youtube",
     "caste cette video youtube https://youtu.be/dQw4w9WgXcQ",
     "catt.cast_youtube", {}, {}),

    ("CATT/youtube", "diffuse video",
     "diffuse cette video sur la tv https://youtu.be/dQw4w9WgXcQ",
     "catt.cast_youtube", {}, {}),

    # ================================================================
    # CATT - controles playback
    # ================================================================
    ("CATT/control", "arrete cast",
     "arrete le cast",
     "catt.cast_stop", {}, {}),

    ("CATT/control", "pause cast",
     "mets le cast en pause",
     "catt.cast_pause", {}, {}),

    ("CATT/control", "reprends cast",
     "reprends le cast",
     "catt.cast_resume", {}, {}),

    ("CATT/control", "avance 30s",
     "avance de 30 secondes dans le cast",
     "catt.cast_seek", {}, {}),

    ("CATT/control", "baisse volume diffusion",
     "baisse le volume de la diffusion",
     "catt.cast_volume", {}, {}),

]


# Outils acceptes a la place de l'attendu : meme effet pour l'utilisateur.
# "mets les lumieres plus fortes" (pluriel) via set_group_brightness est au
# moins aussi juste que set_brightness ; une video YouTube jouee sur la TV
# passe par pylips ou par le Chromecast. Le score STRICT reste publie a cote
# (cle `strict` de chaque resultat) pour rester comparable aux mesures
# anterieures au 2026-09-17.
EQUIVALENCES = {
    "tv.youtube_video": {"catt.cast_youtube"},
    "catt.cast_youtube": {"tv.youtube_video"},
    "hue.set_brightness": {"hue.set_group_brightness"},
    "hue.set_color_rgb": {"hue.set_group_color_rgb", "hue.set_color_preset", "hue.set_group_color_preset"},
    "hue.set_group_color_rgb": {"hue.set_group_color_preset"},   # "chambre en rouge" : preset rouge = rgb rouge
    "hue.turn_on_group": {"hue.turn_on_light"},
    "hue.turn_off_group": {"hue.turn_off_light"},
}


def tool_matches(result_tool, expected_tool):
    """Correspondance stricte (nom court)."""
    if expected_tool is None:
        return result_tool is None
    if result_tool is None:
        return False
    r = result_tool.split(".")[-1] if "." in result_tool else result_tool
    e = expected_tool.split(".")[-1] if "." in expected_tool else expected_tool
    return r == e


def tool_equivalent(result_tool, expected_tool):
    """Correspondance stricte OU equivalence declaree dans EQUIVALENCES."""
    if tool_matches(result_tool, expected_tool):
        return True
    if not result_tool or not expected_tool:
        return False
    return any(tool_matches(result_tool, eq) for eq in EQUIVALENCES.get(expected_tool, ()))


def check_args(result_args, mandatory, optional):
    if result_args is None:
        result_args = {}
    missing_mandatory = []
    for k, v in mandatory.items():
        rv = result_args.get(k)
        if rv is None:
            missing_mandatory.append(k)
        elif v != "" and str(rv) != str(v):
            missing_mandatory.append(f"{k}={v}(got={rv})")
    missing_optional = [k for k in optional if k not in result_args]
    return missing_mandatory, missing_optional


JEUX = {"modeles": "TESTS_LLM", "hors_regles": "TESTS_HORS_REGLES", "hors_regles_2": "TESTS_HORS_REGLES_2",
        "hors_regles_3": "TESTS_HORS_REGLES_3", "hors_regles_4": "TESTS_HORS_REGLES_4",
        "hors_regles_5": "TESTS_HORS_REGLES_5"}


def cas_du_jeu(jeu: str) -> list:
    """Les cas d'un jeu : "modeles" (21, proches des regles) ou "hors_regles" (formulations inedites)."""
    if jeu == "hors_regles":
        from cases_hors_regles import TESTS_HORS_REGLES
        return TESTS_HORS_REGLES
    if jeu == "hors_regles_2":
        from cases_hors_regles_2 import TESTS_HORS_REGLES_2
        return TESTS_HORS_REGLES_2
    if jeu == "hors_regles_3":
        from cases_hors_regles_3 import TESTS_HORS_REGLES_3
        return TESTS_HORS_REGLES_3
    if jeu == "hors_regles_4":
        from cases_hors_regles_4 import TESTS_HORS_REGLES_4
        return TESTS_HORS_REGLES_4
    if jeu == "hors_regles_5":
        from cases_hors_regles_5 import TESTS_HORS_REGLES_5
        return TESTS_HORS_REGLES_5
    if jeu != "modeles":
        raise ValueError(f"jeu inconnu : {jeu} (attendu : {', '.join(JEUX)})")
    return TESTS_LLM


def run_llm_tests(config_path=None, jeu: str = "modeles", reel: bool = False):
    G = "\033[32m"
    Y = "\033[33m"
    R = "\033[31m"
    C = "\033[36m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"

    print(f"\n{BOLD}{'='*70}{RESET}")
    print(f"{BOLD}  CAMPAGNE DE TESTS MCP - PHASE 2 : EPHAISTOS (LLM){RESET}")
    print(f"{BOLD}{'='*70}{RESET}")
    print(f"  {DIM}Tests des RULE_MISS via RAG + Qwen 7B{RESET}\n")

    # Initialisation du pipeline (une seule fois)
    print(f"{C}[INIT]{RESET} Chargement du pipeline RAG (ChromaDB + modeles)...")
    t0 = time.time()
    chemin_config = Path(config_path) if config_path else Path(__file__).parent.parent / "config.yaml"
    config = RAGConfig.from_yaml(chemin_config)

    # EnhancedPipeline, et non Pipeline : c'est le mode de run.sh, et surtout
    # le seul branche sur le RAG 3-tier. Le Pipeline de base interroge l'index
    # v2, qui ne contient que les 19 outils fedora : aucune requete de cast n'y
    # trouvait de candidat, et le banc mesurait donc ce mauvais branchement
    # plutot que le modele (roadmap-github#72).
    import yaml as _yaml

    from lyra.rag_enhanced import EnhancedPipeline
    from lyra.rag_enhanced.config import RAGEnhancedConfig

    brut = _yaml.safe_load(chemin_config.read_text()) or {}
    enhanced = EnhancedPipeline(
        config=config,
        enhanced_config=RAGEnhancedConfig.from_dict(brut.get("rag_enhanced", {})),
        enabled=True,
        tts_mode=False,
    )
    enhanced.initialize()
    pipeline = enhanced._pipeline_v2   # porte _ephaistos
    pipeline._rag_3tier = enhanced._rag_3tier
    print(f"{G}[INIT]{RESET} Pipeline pret ({time.time()-t0:.1f}s)\n")

    results = []
    categories = {}
    erreurs_techniques: list[str] = []

    cas = cas_du_jeu(jeu)
    if reel:
        print(f"{C}[MODE]{RESET} chemin reel : EnhancedPipeline.process (classificateur, contexte, LYRA) -- une session par cas\n")
    for i, (cat, desc, query, expected_tool, mandatory_args, optional_args) in enumerate(cas, 1):
        print(f"{DIM}[{i:02d}/{len(cas)}] {desc}: {query[:55]}...{RESET}" if len(query) > 55
              else f"{DIM}[{i:02d}/{len(cas)}] {desc}: {query}{RESET}")

        t_start = time.time()
        refus_vm = False
        try:
          if reel:
            # Le chemin de production, de bout en bout jusqu'a la proposition
            # d'action (pas d'execution : le tool_call attend une confirmation
            # que personne ne donne). Une session neuve par cas.
            # process() ouvre lui-meme le scope de session_id ("default" sinon) :
            # sans session propre, la question laissee par un cas (choix, clarification)
            # etait relue comme la reponse du cas suivant, et tout partait en vm_clone.
            res = enhanced.process(query, session_id=f"bench-reel-{i}")
            result_tool = (res.tool_call or {}).get("name")
            result_args = (res.tool_call or {}).get("arguments") or {}
            # Le chemin reel verifie que la VM existe : "staging-03" (jeux 3) et
            # "preprod-01" (jeu 2) n'existent pas ici, la reponse "La VM n'existe pas"
            # est la bonne. Compte a part, hors du score.
            refus_vm = bool(res.error) and "n'existe pas" in (res.response or "")
            if not refus_vm and str(expected_tool).startswith("fedora.vm_"):
                from lyra.models import ephaistos_exp as _exp
                cites = _exp.noms_de_machines(query, inventaire=True)
                if cites and not any(n in _exp.inventaire_vm() for n in cites):
                    refus_vm = True   # workflow (clone) : la source n'existe pas, il questionne
            if result_tool is None and res.error is None and res.pending_args:
                result_tool = None   # clarification demandee : compte comme echec sauf expected None
          else:
            # Recuperer les specs RAG
            resultats = pipeline._rag_3tier.cascade_search(query)
            # Meme construction que le pipeline enrichi (specs_pour_ephaistos) :
            # le banc et la production ne doivent plus pouvoir diverger.
            from lyra.rag_enhanced.rag_3tier import specs_pour_ephaistos
            specs = specs_pour_ephaistos(resultats)
            noms_outils = [s.split(":", 1)[0].strip() for s in specs]

            if not specs:
                result = {"tool": None, "arguments": {}, "error": "Aucun spec RAG"}
                result_tool = None
                result_args = {}
            else:
                # Appeler EPHAISTOS directement
                from lyra.utils.toon import toon_encode_specs
                ephaistos_model = pipeline.config.models.ephaistos.name
                # Les variantes LYRA_EXP agissent sur le chemin des specs
                # compactes ; avec TOON, analyze() les ignore. Pour comparer les
                # modeles a configuration egale, pas de TOON des qu'une variante
                # est active.
                from lyra.models import ephaistos_exp as _exp
                use_toon = "0.5b" not in ephaistos_model and not _exp.actives()
                specs_toon = toon_encode_specs(specs) if use_toon else None

                analysis = pipeline._ephaistos.analyze_with_retry(
                    user_query=query,
                    mcp_specs=specs,
                    specs_toon=specs_toon
                )
                result_tool = analysis.tool
                result_args = analysis.arguments or {}

                # Prefixe serveur : on reutilise la resolution du pipeline,
                # deja couverte par des tests, contre les noms du 3-tier.
                if result_tool:
                    resolu = _resoudre_nom_outil(result_tool, [], noms_outils)
                    if resolu:
                        result_tool = resolu

        except Exception as e:
            # Une panne technique (API deplacee, RAG muet) n'est PAS un echec
            # du modele : elle etait comptee en LLM_FAIL et le banc publiait
            # un 0 % qui accusait le modele a tort (constate le 2026-09-17,
            # _retrieve_specs avait disparu du pipeline).
            erreurs_techniques.append(f"{desc}: {type(e).__name__}: {e}")
            result_tool = None
            result_args = {}
            print(f"  {R}ERREUR: {e}{RESET}")

        elapsed = time.time() - t_start

        # Evaluer le resultat
        strict = tool_matches(result_tool, expected_tool)
        tool_ok = tool_equivalent(result_tool, expected_tool)
        missing_mand, missing_opt = check_args(result_args, mandatory_args, optional_args)

        if refus_vm:
            status = "LLM_REFUS"
        elif result_tool is None:
            status = "LLM_FAIL"
        elif not tool_ok:
            status = "LLM_FAIL"
        elif missing_mand:
            status = "LLM_FAIL"
        elif missing_opt:
            status = "LLM_PARTIAL"
        else:
            status = "LLM_PASS"

        color = G if status == "LLM_PASS" else (Y if status == "LLM_PARTIAL" else (DIM if status == "LLM_REFUS" else R))
        tool_str = (result_tool or "NONE").split(".")[-1][:18].ljust(19)
        pad = desc[:35].ljust(36)
        args_str = ""
        if missing_mand:
            args_str = f" {R}ARGS_MANQUANTS={missing_mand}{RESET}"
        elif missing_opt:
            args_str = f" {Y}OPT_MISS={missing_opt}{RESET}"
        elif result_tool and not tool_ok:
            exp_short = (expected_tool or "").split(".")[-1]
            args_str = f" {R}attendu={exp_short}{RESET}"
        elif tool_ok and not strict:
            args_str = f" {Y}EQUIV de {(expected_tool or '').split('.')[-1]}{RESET}"

        print(f"  {color}[{status:<10}]{RESET} {DIM}{pad}{RESET} -> {tool_str}{args_str} {DIM}({elapsed:.1f}s){RESET}")

        entry = {
            "cat": cat, "desc": desc, "query": query,
            "expected_tool": expected_tool, "result_tool": result_tool,
            "result_args": result_args, "mandatory_args": mandatory_args,
            "missing_mand": missing_mand, "missing_opt": missing_opt,
            "status": status, "strict": strict and status == "LLM_PASS", "elapsed": elapsed
        }
        results.append(entry)
        categories.setdefault(cat.split("/")[0], []).append(entry)

    # Score final
    print(f"\n{BOLD}{'='*70}{RESET}")
    print(f"{BOLD}  SCORES PAR CATEGORIE (LLM){RESET}")
    print(f"{BOLD}{'='*70}{RESET}")

    total_pass = total_partial = total_fail = total_refus = 0
    for cat_name, entries in sorted(categories.items()):
        refus = sum(1 for e in entries if e["status"] == "LLM_REFUS")
        total_refus += refus
        n = len(entries) - refus
        p = sum(1 for e in entries if e["status"] == "LLM_PASS")
        pa = sum(1 for e in entries if e["status"] == "LLM_PARTIAL")
        f = sum(1 for e in entries if e["status"] == "LLM_FAIL")
        total_pass += p; total_partial += pa; total_fail += f
        score_pct = round(100 * (p + 0.5 * pa) / n) if n else 0
        bar = f"{G}{'#' * p}{Y}{'~' * pa}{R}{'-' * f}{RESET}"
        print(f"  {BOLD}{cat_name:<8}{RESET} {bar} "
              f"{G}{p}P{RESET} {Y}{pa}~{RESET} {R}{f}F{RESET} / {n}  [{score_pct}%]")

    total = len(results) - total_refus
    score_final = round(100 * (total_pass + 0.5 * total_partial) / total) if total else 0
    if total_refus:
        print(f"\n  {DIM}{total_refus} cas hors score : VM inexistante, refus correct du chemin reel{RESET}")
    print(f"\n{BOLD}{'='*70}{RESET}")
    print(f"{BOLD}  SCORE LLM : {G}{total_pass}{RESET}{BOLD} LLM_PASS  "
          f"{Y}{total_partial}{RESET}{BOLD} LLM_PARTIAL  "
          f"{R}{total_fail}{RESET}{BOLD} LLM_FAIL  / {total} tests{RESET}")
    print(f"{BOLD}  SCORE LLM : {score_final}%{RESET}\n")

    # Sauvegarder rapport texte
    report_path = Path(__file__).parent / "test_campaign_llm_report.txt"
    with open(report_path, "w") as f:
        f.write("CAMPAGNE DE TESTS MCP - PHASE 2 : EPHAISTOS (LLM)\n")
        f.write("=" * 70 + "\n\n")
        f.write("Tests des requetes RULE_MISS via RAG + EPHAISTOS (Qwen 7B)\n\n")
        for r in results:
            f.write(f"[{r['status']:<10}] {r['desc']}\n")
            f.write(f"  Requete  : \"{r['query']}\"\n")
            f.write(f"  Attendu  : {r['expected_tool']}\n")
            f.write(f"  Obtenu   : {r['result_tool']}\n")
            if r['result_args']:
                f.write(f"  Args     : {r['result_args']}\n")
            if r['missing_mand']:
                f.write(f"  MANQUANT : {r['missing_mand']}\n")
            f.write("\n")
        f.write("=" * 70 + "\n")
        f.write(f"LLM_PASS: {total_pass}  LLM_PARTIAL: {total_partial}  LLM_FAIL: {total_fail}\n")
        f.write(f"SCORE LLM: {score_final}%\n")

    print(f"Rapport sauvegarde : {report_path}")
    if erreurs_techniques:
        print(f"\n{R}{len(erreurs_techniques)} panne(s) technique(s) — "
              f"ces cas ne mesurent PAS le modele :{RESET}")
        for ligne in erreurs_techniques[:5]:
            print(f"  {ligne}")
    return results, categories, score_final, erreurs_techniques


def _config_derivee(ephaistos: str | None, lyra: str | None) -> str | None:
    """Ecrit une copie de config.yaml avec d'autres modeles.

    config.yaml n'est jamais modifie : c'est la configuration de production.
    """
    if not ephaistos and not lyra:
        return None
    import tempfile

    import yaml as _yaml
    racine = Path(__file__).parent.parent
    cfg = _yaml.safe_load((racine / "config.yaml").read_text()) or {}
    cfg.setdefault("models", {})
    if ephaistos:
        cfg["models"].setdefault("ephaistos", {})["name"] = ephaistos
    if lyra:
        cfg["models"].setdefault("lyra", {})["name"] = lyra
    tmp = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
    _yaml.safe_dump(cfg, tmp, allow_unicode=True)
    tmp.close()
    return tmp.name


def main() -> None:
    import argparse
    from collections import Counter

    parser = argparse.ArgumentParser(
        description="Banc des requetes RULE_MISS : celles ou EPHAISTOS travaille vraiment.")
    parser.add_argument("--ephaistos", default=None,
                        help="Modele EPHAISTOS a mesurer (ex: qwen2.5-coder:7b)")
    parser.add_argument("--lyra", default=None, help="Modele LYRA a mesurer")
    parser.add_argument("--json", action="store_true",
                        help="Publie le resultat dans benchmarks/results/")
    parser.add_argument("--jeu", default="modeles", choices=sorted(JEUX),
                        help="jeu de cas : modeles (21, proches des regles) ou hors_regles (inedites)")
    parser.add_argument("--reel", action="store_true",
                        help="passer par EnhancedPipeline.process (le chemin du demon) au lieu d'appeler EPHAISTOS directement")
    args = parser.parse_args()

    chemin = _config_derivee(args.ephaistos, args.lyra)
    if chemin:
        print(f"Configuration derivee : ephaistos={args.ephaistos or '(inchange)'}")

    debut = time.time()
    results, categories, score_final, pannes = run_llm_tests(chemin, jeu=args.jeu, reel=args.reel)
    duree = time.time() - debut

    if args.json and pannes:
        print(f"\nPublication refusee : {len(pannes)} panne(s) technique(s). "
              "Un banc en panne ne publie pas de chiffre.")
        sys.exit(2)

    if args.json:
        sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
        from bench_common import ecrire_resultat, modeles  # noqa: E402

        actifs = modeles()
        if args.ephaistos:
            actifs["ephaistos"] = args.ephaistos
        if args.lyra:
            actifs["lyra"] = args.lyra

        statuts = Counter(r["status"] for r in results)
        par_cat = {}
        for r in results:
            par_cat.setdefault(r["cat"].split("/")[0], Counter())[r["status"]] += 1

        total = len(results)
        slug = actifs.get("ephaistos", "defaut").replace(":", "-")
        # Une mesure prise avec des variantes LYRA_EXP ne remplace pas la
        # mesure de reference du meme modele : fichier distinct, variantes
        # enregistrees dans le resultat.
        from lyra.models import ephaistos_exp as _exp
        variantes = sorted(_exp.actives())
        if variantes:
            slug += "-exp"
        if args.jeu != "modeles":
            slug += f"-{args.jeu.replace('_', '')}"
        chemin_sortie = ecrire_resultat("modeles", {
            "jeu": args.jeu,
            "variantes": variantes,
            "banc": "RULE_MISS via EPHAISTOS (les regles ne couvrent pas ces requetes)",
            "cas": total,
            "statuts": dict(statuts),
            "taux_pass": round(statuts["LLM_PASS"] / total, 4) if total else 0.0,
            "score_pondere": score_final,
            "par_categorie": {c: dict(v) for c, v in sorted(par_cat.items())},
            "modeles_mesures": actifs,
            "duree_s": round(duree, 1),
            "duree_inclut_initialisation": True,
        }, suffixe=slug)
        print(f"Resume publie : {chemin_sortie}")


if __name__ == "__main__":
    main()
