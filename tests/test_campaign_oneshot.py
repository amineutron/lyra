#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# NOTE: lancer avec le venv lyra: .venv/bin/python tests/test_campaign_oneshot.py
"""
Campagne de tests ONE-SHOT - Lyra RAG v2
=========================================
Pour chaque test du campaign MCP, execute les deux phases:

  Phase 1 (DRY-RUN)  : _rule_based_detect uniquement (sans Ollama, <1s total)
  Phase 2 (ONE-SHOT) : pipeline complet avec Ollama + RAG + regles + EPHAISTOS
                       (init unique ~5-10s, puis ~1-3s par requete)

Avantages vs test_campaign_mcp.py :
  - Detecte les bugs pipeline qui passent les regles mais echouent en production
  - Montre les divergences dry-run vs realite (ex: IntentClassifier qui classe mal)
  - Source de chaque decision : "rule" (sans LLM) ou "ephaistos" (Qwen)

Usage:
  python3 tests/test_campaign_oneshot.py                         # Tous les tests
  python3 tests/test_campaign_oneshot.py --category FEDORA       # Une categorie
  python3 tests/test_campaign_oneshot.py --fails-only            # Affiche seulement les echecs
  python3 tests/test_campaign_oneshot.py --dry-only              # Phase 1 uniquement (rapide)
  python3 tests/test_campaign_oneshot.py --oneshot-only          # Phase 2 uniquement

Notes:
  - Le pipeline est initialise une seule fois (Ollama, ChromaDB, SentenceTransformer, MCP)
  - Aucune action MCP n'est executee : pipeline.process() retourne la decision sans executer
  - Requiert Ollama actif avec les modeles configures dans config.yaml
"""

import sys
import time
import argparse
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# --- Path setup ---
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))

from test_campaign_mcp import TESTS, normalize, tool_matches, check_args

# --- Constantes statut ---
PASS      = "PASS"
PARTIAL   = "PARTIAL"
FAIL      = "FAIL"
RULE_MISS = "RULE_MISS"
ERROR     = "ERROR"    # Exception pendant le one-shot


# --- Evaluation ---

def eval_result(result_tool, result_args, result_pending, expected_tool, mandatory_args, optional_args):
    """Evalue un resultat de test (dry-run ou one-shot)."""
    # Combiner args connus + pending comme "non extrait" pour les mandatory checks
    all_args = dict(result_args or {})

    if expected_tool is None:
        return PASS if result_tool is None else FAIL
    if result_tool is None:
        return RULE_MISS
    if not tool_matches(result_tool, expected_tool):
        return FAIL

    missing_mand, missing_opt = check_args(all_args, mandatory_args, optional_args)

    # Aussi FAIL si un mandatory_arg est dans pending (pas extrait de la requete)
    for k in list(mandatory_args.keys()):
        if k in (result_pending or []) and k not in [m.split("=")[0] for m in missing_mand]:
            missing_mand.append(f"{k}(pending)")

    if missing_mand:
        return FAIL
    if missing_opt:
        return PARTIAL
    return PASS


# --- Phase 1 : DRY-RUN ---

def run_dryrun_phase():
    """Execute la phase dry-run pour tous les tests.

    Appelle Pipeline._rule_based_detect + _enrich_optional_args
    sans initialiser Ollama ni ChromaDB.

    Returns:
        list[dict]: resultats bruts par test
    """
    from lyra.core.pipeline import Pipeline

    results = []
    for cat, desc, query, expected_tool, mandatory_args, optional_args in TESTS:
        raw_q = normalize(query)
        analysis = Pipeline._rule_based_detect(raw_q)
        if analysis is not None:
            analysis = Pipeline._enrich_optional_args(raw_q, analysis)

        result_tool = analysis.tool if analysis else None
        result_args = analysis.arguments if analysis else {}
        result_pending = analysis.missing_args if analysis else []
        reasoning = (analysis.reasoning or "") if analysis else ""

        status = eval_result(result_tool, result_args, result_pending,
                             expected_tool, mandatory_args, optional_args)
        results.append({
            "cat": cat, "desc": desc, "query": query,
            "expected_tool": expected_tool,
            "result_tool": result_tool,
            "result_args": result_args,
            "result_pending": result_pending,
            "status": status,
            "reasoning": reasoning,
            "source": "rule" if reasoning.startswith("rule:") else ("ephaistos" if result_tool else "no_match"),
        })
    return results


# --- Phase 2 : ONE-SHOT ---

# Noms de VMs fictifs utilises dans les tests (non existants sur l'hote)
_TEST_VM_NAMES = {
    "preprod-01", "preprod-09",
    "sandbox-01", "sandbox-02",
    # sandbox-03, test-clone, test-cow, neutron-clone, backup-system sont des
    # DESTINATIONS de clone/export -- elles ne doivent PAS exister pour eviter
    # que le workflow vm_clone declenche le cas "nom deja pris"
    "test-server", "test-vm",
    "neutron",
    "system-clone-final", "prod-clone",
    "electron-backup-test",
    "arch-base", "fedora-base", "ubuntu-base", "neutron-template-05",
}


def _mock_vm_calls(pipeline):
    """Patche les appels MCP reels du pipeline pour les tests.

    Remplace les methodes et fonctions standalone qui interrogent les VMs
    reelles par des stubs previsibles.
    Les VMs fictives des tests sont toutes considerees comme existantes
    et eteintes.
    """
    import types
    import lyra.core.workflows.vm_clone as _wf_clone
    import lyra.core.workflows.vm_snapshot as _wf_snapshot

    v2 = pipeline._pipeline_v2 if hasattr(pipeline, "_pipeline_v2") else pipeline

    # _validate_vm_existence: toujours OK (pas d'erreur "VM inexistante")
    v2._validate_vm_existence = types.MethodType(
        lambda self, analysis, query: None, v2
    )
    # _get_vm_state: VM fictive = eteinte, pas d'IP
    v2._get_vm_state = types.MethodType(
        lambda self, vm_name: {"running": False, "ip": None}, v2
    )
    # _get_existing_vm_names: retourne le set des VMs de test
    v2._get_existing_vm_names = types.MethodType(
        lambda self: list(_TEST_VM_NAMES), v2
    )

    # Patch les fonctions standalone importees par les workflows (from ..validation import ...)
    # Ces references sont dans l'espace de noms du module workflow, pas celui du pipeline
    _wf_clone.get_existing_vm_names = lambda hestia: list(_TEST_VM_NAMES)
    _wf_clone.get_vm_state = lambda hestia, vm_name: {"running": False, "ip": None}
    _wf_snapshot.get_existing_vm_names = lambda hestia: list(_TEST_VM_NAMES)


def init_pipeline():
    """Initialise le pipeline complet (Ollama + RAG + MCP).

    Les appels MCP reels (validation VM, etat) sont patched pour
    que les tests fonctionnent sans infrastructure reelle.

    Returns:
        pipeline instance prete a l'emploi
    Raises:
        Exception si l'init echoue (modele manquant, etc.)
    """
    import yaml
    from lyra.core.config import RAGConfig

    config_path = ROOT / "config.yaml"
    config = RAGConfig.from_yaml(config_path)

    # Lire la config enhanced depuis YAML
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    enhanced_raw = cfg.get("rag_enhanced", {})

    # Toujours utiliser EnhancedPipeline (c'est le mode par defaut de run.sh)
    from lyra.rag_enhanced import EnhancedPipeline
    from lyra.rag_enhanced.config import RAGEnhancedConfig
    enhanced_config = RAGEnhancedConfig.from_dict(enhanced_raw)

    pipeline = EnhancedPipeline(
        config=config,
        enhanced_config=enhanced_config,
        enabled=enhanced_config.enabled,
        tts_mode=False
    )
    pipeline.initialize()
    _mock_vm_calls(pipeline)
    return pipeline


def run_oneshot_single(pipeline, query: str, expected_tool: str,
                       mandatory_args: dict, optional_args: dict) -> dict:
    """Traite une requete via le pipeline complet.

    Args:
        pipeline: Pipeline initialise
        query: Requete utilisateur (non normalisee, telle quelle)
        expected_tool: Outil attendu
        mandatory_args: Args obligatoires
        optional_args: Args optionnels

    Returns:
        dict avec status, result_tool, result_args, source, etc.
    """
    from lyra.core.types import QueryType

    # Reset session avant chaque test pour eviter la contamination
    # (les workflows interactifs laissent pending_action/pending_choice en session)
    v2 = pipeline._pipeline_v2 if hasattr(pipeline, "_pipeline_v2") else pipeline
    v2._session.clear()

    t0 = time.perf_counter()
    try:
        result = pipeline.process(query)
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        return {
            "result_tool": None, "result_args": {}, "result_pending": [],
            "status": ERROR, "source": "error",
            "reasoning": str(exc), "elapsed": elapsed,
            "error": str(exc),
        }
    elapsed = time.perf_counter() - t0

    # Extraire les infos du resultat
    if result.tool_call:
        result_tool = result.tool_call.get("name")
        result_args = result.tool_call.get("arguments", {})
    else:
        result_tool = None
        result_args = {}

    result_pending = getattr(result, "pending_args", []) or []
    meta = getattr(result, "analysis_meta", None) or {}
    source = meta.get("source", "unknown")
    reasoning = meta.get("reasoning", "")

    # Si le pipeline a classifie comme KNOWLEDGE alors qu'on attend une action
    if result.query_type == QueryType.KNOWLEDGE and expected_tool is not None:
        return {
            "result_tool": None, "result_args": {}, "result_pending": [],
            "status": FAIL, "source": source,
            "reasoning": "IntentClassifier: KNOWLEDGE (attendu ACTION)",
            "elapsed": elapsed, "error": None,
        }

    status = eval_result(result_tool, result_args, result_pending,
                         expected_tool, mandatory_args, optional_args)

    return {
        "result_tool": result_tool,
        "result_args": result_args,
        "result_pending": result_pending,
        "status": status,
        "source": source,
        "reasoning": reasoning,
        "elapsed": elapsed,
        "error": None,
    }


def run_oneshot_phase(pipeline, filter_category: Optional[str] = None) -> list:
    """Execute la phase one-shot pour tous les tests.

    Args:
        pipeline: Pipeline initialise
        filter_category: Si donne, limite aux tests de cette categorie (ex: "FEDORA")

    Returns:
        list[dict]: resultats bruts par test
    """
    results = []
    for cat, desc, query, expected_tool, mandatory_args, optional_args in TESTS:
        top_cat = cat.split("/")[0]
        if filter_category and top_cat.upper() != filter_category.upper():
            results.append(None)  # Placeholder pour aligner avec dry-run
            continue

        r = run_oneshot_single(pipeline, query, expected_tool, mandatory_args, optional_args)
        r.update({"cat": cat, "desc": desc, "query": query, "expected_tool": expected_tool})
        results.append(r)
    return results


# --- Rapport ---

def _status_color(status: str, no_color: bool = False) -> str:
    if no_color:
        return ""
    colors = {
        PASS: "\033[32m",
        PARTIAL: "\033[33m",
        FAIL: "\033[31m",
        RULE_MISS: "\033[34m",
        ERROR: "\033[35m",
    }
    return colors.get(status, "")


RESET = "\033[0m"
BOLD  = "\033[1m"
DIM   = "\033[2m"
CYAN  = "\033[36m"
RED   = "\033[31m"
GREEN = "\033[32m"
YELLOW= "\033[33m"


def print_report(dry_results: list, one_results: list,
                 fails_only: bool = False, no_color: bool = False):
    """Affiche le rapport combine DRY-RUN + ONE-SHOT."""

    def c(color): return "" if no_color else color

    total = len(TESTS)

    # --- Compteurs ---
    def count(results, status):
        return sum(1 for r in results if r and r.get("status") == status)

    dry_pass    = count(dry_results, PASS)
    dry_partial = count(dry_results, PARTIAL)
    dry_fail    = count(dry_results, FAIL)
    dry_miss    = count(dry_results, RULE_MISS)

    one_pass    = count(one_results, PASS)
    one_partial = count(one_results, PARTIAL)
    one_fail    = count(one_results, FAIL)
    one_miss    = count(one_results, RULE_MISS)
    one_error   = count(one_results, ERROR)
    one_skip    = sum(1 for r in one_results if r is None)

    # Coherence: dry et oneshot ont le meme statut
    coherent = sum(
        1 for d, o in zip(dry_results, one_results)
        if d and o and d["status"] == o["status"]
    )
    compared = sum(1 for d, o in zip(dry_results, one_results) if d and o)

    sep = "=" * 70

    print(f"\n{c(BOLD)}{sep}{c(RESET)}")
    print(f"  {c(BOLD)}TEST CAMPAIGN ONE-SHOT - Lyra RAG v2{c(RESET)}")
    print(f"  {total} tests | Phase 1: dry-run (rules) | Phase 2: one-shot (pipeline)")
    print(f"{c(BOLD)}{sep}{c(RESET)}")

    # --- Details par test ---
    prev_top = None
    for i, (dry, one) in enumerate(zip(dry_results, one_results)):
        if dry is None:
            continue
        cat = dry["cat"]
        top_cat = cat.split("/")[0]
        sub_cat = cat.split("/")[1] if "/" in cat else ""
        query = dry["query"]
        desc = dry["desc"]

        ds = dry["status"]
        os_ = one["status"] if one else "SKIP"

        # Filtrage
        if fails_only and ds == PASS and os_ == PASS:
            continue

        # Separateur categorie
        if top_cat != prev_top:
            print(f"\n  {c(BOLD)}{c(CYAN)}--- {top_cat} ---{c(RESET)}")
            prev_top = top_cat

        # Ligne de resultat
        num = f"{i+1:>3}/{total}"
        dry_label = f"{c(_status_color(ds, no_color))}{ds:<9}{c(RESET)}"
        one_label = f"{c(_status_color(os_, no_color))}{os_:<9}{c(RESET)}" if one else f"{c(DIM)}SKIP     {c(RESET)}"

        diverge_marker = ""
        if one and ds != os_:
            diverge_marker = f" {c(YELLOW)}[!]{c(RESET)}"

        short_q = query[:50].ljust(50) if len(query) <= 50 else query[:47] + "..."
        print(f"  [{num}] DRY:{dry_label} ONE:{one_label} {c(DIM)}{short_q}{c(RESET)}{diverge_marker}")

        # Details en cas d'echec ou divergence
        if ds != PASS or (one and os_ != PASS):
            if one and one.get("result_tool") and one["result_tool"] != dry["result_tool"]:
                print(f"          DRY tool : {dry['result_tool'] or 'none'}")
                print(f"          ONE tool : {one['result_tool'] or 'none'} [{one.get('source','?')}]")
            elif ds != PASS:
                print(f"          tool     : {dry['result_tool'] or 'none'}")
            if one and os_ == ERROR:
                print(f"          {c(RED)}ERROR: {one.get('error','')}{c(RESET)}")
            if one and os_ == FAIL and one.get("reasoning"):
                if "IntentClassifier" in one["reasoning"]:
                    print(f"          {c(RED)}{one['reasoning']}{c(RESET)}")

    # --- Scores ---
    print(f"\n{c(BOLD)}{sep}{c(RESET)}")
    print(f"  {c(BOLD)}SCORE FINAL{c(RESET)}")
    print(f"{c(BOLD)}{sep}{c(RESET)}")
    print(f"  {'':20}  {'DRY-RUN':>12}  {'ONE-SHOT':>12}")
    print(f"  {'-'*46}")

    def pct(n, d): return f"{100*n//d}%" if d > 0 else "N/A"

    one_done = total - one_skip
    print(f"  {c(GREEN)}PASS{c(RESET)}{'':16}  {dry_pass:>6}/{total} {pct(dry_pass,total):>4}  {one_pass:>6}/{one_done} {pct(one_pass,one_done):>4}")
    print(f"  {c(YELLOW)}PARTIAL{c(RESET)}{'':13}  {dry_partial:>6}/{total} {pct(dry_partial,total):>4}  {one_partial:>6}/{one_done} {pct(one_partial,one_done):>4}")
    print(f"  RULE_MISS{'':11}  {dry_miss:>6}/{total} {pct(dry_miss,total):>4}  {one_miss:>6}/{one_done} {pct(one_miss,one_done):>4}")
    print(f"  {c(RED)}FAIL{c(RESET)}{'':16}  {dry_fail:>6}/{total} {pct(dry_fail,total):>4}  {one_fail:>6}/{one_done} {pct(one_fail,one_done):>4}")
    if one_error:
        print(f"  {c(RED)}ERROR (exception){c(RESET)}  {' ':>10}  {one_error:>6}/{one_done}")
    if one_skip:
        print(f"  {c(DIM)}SKIP (filtre){c(RESET)}{'':8}  {' ':>10}  {one_skip:>6}/{total}")

    if compared > 0:
        print(f"\n  Coherence DRY==ONE : {coherent}/{compared} ({100*coherent//compared}%)")

    # --- Divergences ---
    divergences = [
        (i, dry_results[i], one_results[i])
        for i in range(total)
        if dry_results[i] and one_results[i]
        and dry_results[i]["status"] != one_results[i]["status"]
    ]
    if divergences:
        print(f"\n{c(BOLD)}{sep}{c(RESET)}")
        print(f"  {c(BOLD)}{c(YELLOW)}DIVERGENCES (dry != oneshot){c(RESET)}")
        print(f"{c(BOLD)}{sep}{c(RESET)}")
        for i, dry, one in divergences:
            print(f"\n  [{i+1:>3}] {dry['cat']} | {dry['desc']}")
            print(f"       Query    : {dry['query']}")
            print(f"       Attendu  : {dry['expected_tool']}")
            print(f"       DRY      : {c(_status_color(dry['status'], no_color))}{dry['status']}{c(RESET)} -> {dry['result_tool'] or 'none'}")
            one_src = f" [{one.get('source','?')} {one.get('elapsed',0):.1f}s]" if one.get('elapsed') else ""
            print(f"       ONE-SHOT : {c(_status_color(one['status'], no_color))}{one['status']}{c(RESET)} -> {one['result_tool'] or 'none'}{one_src}")
            if one.get("reasoning"):
                print(f"       Raison   : {one['reasoning'][:80]}")
    print(f"{c(BOLD)}{sep}{c(RESET)}\n")


# --- Main ---

def main():
    parser = argparse.ArgumentParser(
        description="Campagne de tests ONE-SHOT Lyra RAG v2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemples:\n"
            "  python3 tests/test_campaign_oneshot.py\n"
            "  python3 tests/test_campaign_oneshot.py --category FEDORA\n"
            "  python3 tests/test_campaign_oneshot.py --fails-only\n"
            "  python3 tests/test_campaign_oneshot.py --dry-only\n"
        )
    )
    parser.add_argument("--category", "-c", default=None,
                        help="Filtrer par categorie (ex: FEDORA, HUE, TV, CATT, DENON, BACKUP)")
    parser.add_argument("--fails-only", action="store_true",
                        help="N'afficher que les tests avec au moins un echec")
    parser.add_argument("--dry-only", action="store_true",
                        help="Phase 1 uniquement (sans Ollama, rapide)")
    parser.add_argument("--oneshot-only", action="store_true",
                        help="Phase 2 uniquement (sans re-afficher dry-run)")
    parser.add_argument("--no-color", action="store_true", help="Desactiver les couleurs ANSI")
    args = parser.parse_args()

    # --- Phase 1 : DRY-RUN ---
    print(f"\n{BOLD}Phase 1 : DRY-RUN (rules uniquement){RESET}", flush=True)
    t0 = time.perf_counter()
    dry_results = run_dryrun_phase()
    dry_elapsed = time.perf_counter() - t0
    dry_pass = sum(1 for r in dry_results if r["status"] == PASS)
    print(f"  Termine en {dry_elapsed:.2f}s  |  {dry_pass}/{len(TESTS)} PASS", flush=True)

    if args.dry_only:
        # Creer des placeholders pour le rapport
        one_results = [None] * len(TESTS)
        print_report(dry_results, one_results, fails_only=args.fails_only, no_color=args.no_color)
        sys.exit(0 if dry_pass == len(TESTS) else 1)

    # --- Phase 2 : ONE-SHOT ---
    print(f"\n{BOLD}Phase 2 : ONE-SHOT (pipeline complet){RESET}", flush=True)
    print("  Initialisation Ollama + RAG + MCP...", end="", flush=True)
    t_init = time.perf_counter()
    try:
        pipeline = init_pipeline()
    except Exception as exc:
        print(f"\n  {RED}ERREUR init pipeline: {exc}{RESET}")
        print("  Verifiez qu'Ollama est actif et que les modeles sont disponibles.")
        sys.exit(2)
    init_elapsed = time.perf_counter() - t_init
    print(f" OK ({init_elapsed:.1f}s)", flush=True)

    # Filtrer les tests si --category
    total_filtered = sum(
        1 for cat, *_ in TESTS
        if not args.category or cat.split("/")[0].upper() == args.category.upper()
    )
    print(f"  Execution de {total_filtered} tests...", flush=True)

    one_results = []
    t_run = time.perf_counter()
    for idx, (cat, desc, query, expected_tool, mandatory_args, optional_args) in enumerate(TESTS):
        top_cat = cat.split("/")[0]
        if args.category and top_cat.upper() != args.category.upper():
            one_results.append(None)
            continue

        # Progression inline
        print(f"  [{idx+1:>3}/{len(TESTS)}] {query[:55]:<55}", end="\r", flush=True)

        r = run_oneshot_single(pipeline, query, expected_tool, mandatory_args, optional_args)
        r.update({"cat": cat, "desc": desc, "query": query, "expected_tool": expected_tool})
        one_results.append(r)

    run_elapsed = time.perf_counter() - t_run
    one_pass = sum(1 for r in one_results if r and r.get("status") == PASS)
    one_done = sum(1 for r in one_results if r is not None)
    print(f"  Termine en {run_elapsed:.1f}s  |  {one_pass}/{one_done} PASS{' ' * 20}", flush=True)

    # --- Rapport ---
    print_report(dry_results, one_results, fails_only=args.fails_only, no_color=args.no_color)

    # Code retour: 0 si tout PASS, 1 sinon
    all_pass = (dry_pass == len(TESTS)) and (one_pass == one_done)
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
