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
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lyra.core.pipeline import Pipeline
from lyra.core.config import RAGConfig

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

    ("TV/ambilight", "couleur ambilight",
     "mets l ambilight en bleu",
     "tv.ambilight_set_color", {}, {}),

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


def tool_matches(result_tool, expected_tool):
    if expected_tool is None:
        return result_tool is None
    if result_tool is None:
        return False
    r = result_tool.split(".")[-1] if "." in result_tool else result_tool
    e = expected_tool.split(".")[-1] if "." in expected_tool else expected_tool
    return r == e


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


def run_llm_tests():
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
    config = RAGConfig.from_yaml(Path(__file__).parent.parent / "config.yaml")
    pipeline = Pipeline(config)
    pipeline.initialize()
    print(f"{G}[INIT]{RESET} Pipeline pret ({time.time()-t0:.1f}s)\n")

    results = []
    categories = {}

    for i, (cat, desc, query, expected_tool, mandatory_args, optional_args) in enumerate(TESTS_LLM, 1):
        print(f"{DIM}[{i:02d}/{len(TESTS_LLM)}] {desc}: {query[:55]}...{RESET}" if len(query) > 55
              else f"{DIM}[{i:02d}/{len(TESTS_LLM)}] {desc}: {query}{RESET}")

        t_start = time.time()
        try:
            # Recuperer les specs RAG
            fused = pipeline._retrieve_specs(query)
            specs = [r.document for r in fused] if fused else []

            if not specs:
                result = {"tool": None, "arguments": {}, "error": "Aucun spec RAG"}
                result_tool = None
                result_args = {}
            else:
                # Appeler EPHAISTOS directement
                from lyra.utils.toon import toon_encode_specs
                ephaistos_model = pipeline.config.models.ephaistos.name
                use_toon = "0.5b" not in ephaistos_model
                specs_toon = toon_encode_specs(specs) if use_toon else None

                analysis = pipeline._ephaistos.analyze_with_retry(
                    user_query=query,
                    mcp_specs=specs,
                    specs_toon=specs_toon
                )
                result_tool = analysis.tool
                result_args = analysis.arguments or {}

                # Ajouter prefixe serveur si manquant
                if result_tool and '.' not in result_tool:
                    for r in fused:
                        meta = r.metadata if isinstance(r.metadata, dict) else {}
                        tool_name = meta.get('name', '')
                        if tool_name.endswith('.' + result_tool) or tool_name == result_tool:
                            result_tool = tool_name
                            break

        except Exception as e:
            result_tool = None
            result_args = {}
            print(f"  {R}ERREUR: {e}{RESET}")

        elapsed = time.time() - t_start

        # Evaluer le resultat
        tool_ok = tool_matches(result_tool, expected_tool)
        missing_mand, missing_opt = check_args(result_args, mandatory_args, optional_args)

        if result_tool is None:
            status = "LLM_FAIL"
        elif not tool_ok:
            status = "LLM_FAIL"
        elif missing_mand:
            status = "LLM_FAIL"
        elif missing_opt:
            status = "LLM_PARTIAL"
        else:
            status = "LLM_PASS"

        color = G if status == "LLM_PASS" else (Y if status == "LLM_PARTIAL" else R)
        tool_str = (result_tool or "NONE").split(".")[-1][:18].ljust(19)
        pad = desc[:35].ljust(36)
        args_str = ""
        if missing_mand:
            args_str = f" {R}ARGS_MANQUANTS={missing_mand}{RESET}"
        elif missing_opt:
            args_str = f" {Y}OPT_MISS={missing_opt}{RESET}"
        elif result_tool and not tool_ok:
            exp_short = (expected_tool or "").split(".")[-1]
            got_short = (result_tool or "NONE").split(".")[-1]
            args_str = f" {R}attendu={exp_short}{RESET}"

        print(f"  {color}[{status:<10}]{RESET} {DIM}{pad}{RESET} -> {tool_str}{args_str} {DIM}({elapsed:.1f}s){RESET}")

        entry = {
            "cat": cat, "desc": desc, "query": query,
            "expected_tool": expected_tool, "result_tool": result_tool,
            "result_args": result_args, "mandatory_args": mandatory_args,
            "missing_mand": missing_mand, "missing_opt": missing_opt,
            "status": status, "elapsed": elapsed
        }
        results.append(entry)
        categories.setdefault(cat.split("/")[0], []).append(entry)

    # Score final
    print(f"\n{BOLD}{'='*70}{RESET}")
    print(f"{BOLD}  SCORES PAR CATEGORIE (LLM){RESET}")
    print(f"{BOLD}{'='*70}{RESET}")

    total_pass = total_partial = total_fail = 0
    for cat_name, entries in sorted(categories.items()):
        n = len(entries)
        p = sum(1 for e in entries if e["status"] == "LLM_PASS")
        pa = sum(1 for e in entries if e["status"] == "LLM_PARTIAL")
        f = sum(1 for e in entries if e["status"] == "LLM_FAIL")
        total_pass += p; total_partial += pa; total_fail += f
        score_pct = round(100 * (p + 0.5 * pa) / n) if n else 0
        bar = f"{G}{'#' * p}{Y}{'~' * pa}{R}{'-' * f}{RESET}"
        print(f"  {BOLD}{cat_name:<8}{RESET} {bar} "
              f"{G}{p}P{RESET} {Y}{pa}~{RESET} {R}{f}F{RESET} / {n}  [{score_pct}%]")

    total = len(results)
    score_final = round(100 * (total_pass + 0.5 * total_partial) / total) if total else 0
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
    return results, categories, score_final


if __name__ == "__main__":
    run_llm_tests()
