#!/usr/bin/env python3
"""
Campagne de tests MCP - Parametres optionnels via EPHAISTOS
===========================================================
Teste si EPHAISTOS (Qwen 7B) extrait correctement les parametres
avances / optionnels quand ils sont mentionnes dans la requete.

Ces cas etaient PARTIAL dans test_campaign_mcp.py (regle detecte le bon outil
mais n'extrait pas les args avances). Ici on les passe directement a EPHAISTOS
avec les specs RAG pour voir s'il comprend et extrait ces arguments.

Statuts:
  PASS    : bon outil + param avance extrait et correct
  PARTIAL : bon outil + param avance absent (EPHAISTOS ne l'a pas extrait)
  FAIL    : mauvais outil ou arg obligatoire manquant

Usage:
  .venv/bin/python tests/test_campaign_opts.py
"""

import sys
import time
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lyra.core.pipeline import Pipeline
from lyra.core.config import RAGConfig

# ============================================================
# Format: (categorie, description, query, expected_tool,
#          mandatory_args, advanced_args)
#
# advanced_args : ces args DOIVENT etre extraits par EPHAISTOS
#                 => traites comme mandatory ici (FAIL si absent)
# ============================================================

TESTS_OPTS = [

    # ================================================================
    # vm_start - wait_ssh / wait_ip
    # ================================================================
    ("FEDORA/vm_start", "wait_ssh explicite",
     "demarre preprod-01 et attends que le ssh soit disponible",
     "fedora.vm_start",
     {"vm_name": "preprod-01", "wait_ssh": True}, {}),

    ("FEDORA/vm_start", "wait_ip explicite",
     "demarre preprod-01 et attends qu il ait une ip",
     "fedora.vm_start",
     {"vm_name": "preprod-01", "wait_ip": True}, {}),

    ("FEDORA/vm_start", "wait_ssh formulation courte",
     "lance preprod-01 attends le ssh",
     "fedora.vm_start",
     {"vm_name": "preprod-01", "wait_ssh": True}, {}),

    # ================================================================
    # vm_stop - force
    # (deja couvert en PASS par la regle, ici on verifie EPHAISTOS seul)
    # ================================================================
    ("FEDORA/vm_stop", "force explicite",
     "arrete de force sandbox-02",
     "fedora.vm_stop",
     {"vm_name": "sandbox-02", "force": True}, {}),

    # ================================================================
    # vm_destroy - keep_storage
    # ================================================================
    ("FEDORA/vm_destroy", "garde le disque",
     "supprime sandbox-01 mais garde le disque",
     "fedora.vm_destroy",
     {"vm_name": "sandbox-01", "keep_storage": True}, {}),

    ("FEDORA/vm_destroy", "keep_storage sans supprimer disk",
     "supprime test-vm sans effacer les fichiers du disque",
     "fedora.vm_destroy",
     {"vm_name": "test-vm", "keep_storage": True}, {}),

    # ================================================================
    # vm_exec - sudo
    # ================================================================
    ("FEDORA/vm_exec", "sudo explicite",
     "execute systemctl restart nginx sur preprod-01 en sudo",
     "fedora.vm_exec",
     {"vm_name": "preprod-01", "sudo": True}, {}),

    ("FEDORA/vm_exec", "sudo avec commande",
     "lance apt-get update sur sandbox-02 avec sudo",
     "fedora.vm_exec",
     {"vm_name": "sandbox-02", "sudo": True}, {}),

    # ================================================================
    # vm_copy - recursive
    # ================================================================
    ("FEDORA/vm_copy", "copie recursive",
     "copie /home/user/projet vers preprod-01 en recursif",
     "fedora.vm_copy",
     {"vm_name": "preprod-01", "recursive": True}, {}),

    ("FEDORA/vm_copy", "copie dossier recursif",
     "transfere le dossier /var/www vers sandbox-02 de facon recursive",
     "fedora.vm_copy",
     {"vm_name": "sandbox-02", "recursive": True}, {}),

    # ================================================================
    # vm_snapshot - live
    # (deja couvert en PASS, verification EPHAISTOS)
    # ================================================================
    ("FEDORA/vm_snapshot", "snapshot live",
     "cree un snapshot live de preprod-01",
     "fedora.vm_snapshot",
     {"vm_name": "preprod-01", "live": True}, {}),

    # ================================================================
    # vm_clone - linked (COW) / start
    # ================================================================
    ("FEDORA/vm_clone", "clone COW linked",
     "clone preprod-01 en test-cow avec cow",
     "fedora.vm_clone",
     {"source_vm": "preprod-01", "new_vm_name": "test-cow", "linked": True}, {}),

    ("FEDORA/vm_clone", "clone linked true",
     "clone preprod-01 en test-linked en mode linked",
     "fedora.vm_clone",
     {"source_vm": "preprod-01", "new_vm_name": "test-linked", "linked": True}, {}),

    ("FEDORA/vm_clone", "clone et demarre apres",
     "clone preprod-01 en test-clone et demarre la vm apres",
     "fedora.vm_clone",
     {"source_vm": "preprod-01", "new_vm_name": "test-clone", "start": True}, {}),

    ("FEDORA/vm_clone", "clone start formulation",
     "duplique sandbox-02 en sandbox-03 et lance la apres",
     "fedora.vm_clone",
     {"source_vm": "sandbox-02", "new_vm_name": "sandbox-03", "start": True}, {}),

    # ================================================================
    # vm_clone_system - dry_run
    # ================================================================
    ("FEDORA/vm_clone_system", "dry_run mode test",
     "clone systeme neutron en neutron-test en mode dry-run",
     "fedora.vm_clone_system",
     {"dry_run": True}, {}),

    ("FEDORA/vm_clone_system", "dry_run sans cloner vraiment",
     "simule le clone systeme de neutron en backup sans l executer vraiment",
     "fedora.vm_clone_system",
     {"dry_run": True}, {}),

    # ================================================================
    # vm_verify - quick / verbose / compare_packages
    # ================================================================
    ("FEDORA/vm_verify", "verification rapide",
     "verifie rapidement neutron-clone",
     "fedora.vm_verify",
     {"vm_name": "neutron-clone", "quick": True}, {}),

    ("FEDORA/vm_verify", "verification verbose",
     "verifie neutron-clone en mode verbeux avec detail",
     "fedora.vm_verify",
     {"vm_name": "neutron-clone", "verbose": True}, {}),

    ("FEDORA/vm_verify", "compare paquets",
     "verifie neutron-clone avec comparaison des paquets installes",
     "fedora.vm_verify",
     {"vm_name": "neutron-clone", "compare_packages": True}, {}),

    # ================================================================
    # vm_status - detailed
    # (couvert par regle, on verifie EPHAISTOS)
    # ================================================================
    ("FEDORA/vm_status", "status detaille",
     "status detaille de preprod-01",
     "fedora.vm_status",
     {"vm_name": "preprod-01", "detailed": True}, {}),

    # ================================================================
    # vm_export - output_path / dry_run
    # ================================================================
    ("FEDORA/vm_export", "export vers chemin",
     "exporte preprod-01 vers /mnt/exports",
     "fedora.vm_export",
     {"vm_name": "preprod-01", "output_path": "/mnt/exports"}, {}),

    ("FEDORA/vm_export", "export dry_run",
     "exporte preprod-01 en mode dry-run sans vraiment exporter",
     "fedora.vm_export",
     {"vm_name": "preprod-01", "dry_run": True}, {}),

    # ================================================================
    # vm_import - start / dry_run
    # ================================================================
    ("FEDORA/vm_import", "import et demarre",
     "importe /home/amineutron/vm-exports/test.tar.gz et demarre la vm apres",
     "fedora.vm_import",
     {"archive_path": "/home/amineutron/vm-exports/test.tar.gz", "start": True}, {}),

    ("FEDORA/vm_import", "import dry_run",
     "importe /home/amineutron/vm-exports/test.tar.gz en dry-run pour tester",
     "fedora.vm_import",
     {"archive_path": "/home/amineutron/vm-exports/test.tar.gz", "dry_run": True}, {}),

    # ================================================================
    # backup_list - type / detailed
    # ================================================================
    ("BACKUP/backup_list", "liste type timeshift",
     "liste mes sauvegardes timeshift",
     "fedora.backup_list",
     {"type": "timeshift"}, {}),

    ("BACKUP/backup_list", "liste type borg",
     "affiche les backups borg",
     "fedora.backup_list",
     {"type": "borg"}, {}),

    ("BACKUP/backup_list", "liste detaillee",
     "affiche les sauvegardes en detail",
     "fedora.backup_list",
     {"detailed": True}, {}),

    # ================================================================
    # backup_create - type / verify / dry_run
    # ================================================================
    ("BACKUP/backup_create", "create type timeshift",
     "cree un backup timeshift de preprod-01",
     "fedora.backup_create",
     {"vm_name": "preprod-01", "type": "timeshift"}, {}),

    ("BACKUP/backup_create", "create avec verification",
     "fais une sauvegarde de preprod-01 avec verification integrite",
     "fedora.backup_create",
     {"vm_name": "preprod-01", "verify": True}, {}),

    ("BACKUP/backup_create", "create dry_run",
     "cree un backup de preprod-01 en dry-run",
     "fedora.backup_create",
     {"vm_name": "preprod-01", "dry_run": True}, {}),

    # ================================================================
    # backup_restore - dry_run / force
    # ================================================================
    ("BACKUP/backup_restore", "restore dry_run",
     "restaure le backup de preprod-01 en dry-run",
     "fedora.backup_restore",
     {"dry_run": True}, {}),

    ("BACKUP/backup_restore", "restore force",
     "restaure de force le backup de preprod-01",
     "fedora.backup_restore",
     {"force": True}, {}),

    # ================================================================
    # backup_verify - deep / quick
    # ================================================================
    ("BACKUP/backup_verify", "verify deep",
     "verifie en profondeur le backup de preprod-01",
     "fedora.backup_verify",
     {"vm_name": "preprod-01", "deep": True}, {}),

    ("BACKUP/backup_verify", "verify quick",
     "verifie rapidement le backup de preprod-01",
     "fedora.backup_verify",
     {"vm_name": "preprod-01", "quick": True}, {}),

    # ================================================================
    # backup_clean - dry_run / keep_last
    # ================================================================
    ("BACKUP/backup_clean", "clean dry_run",
     "nettoie les anciens backups en dry-run sans supprimer vraiment",
     "fedora.backup_clean",
     {"dry_run": True}, {}),

    ("BACKUP/backup_clean", "clean keep_last 3",
     "nettoie les sauvegardes en gardant les 3 dernieres",
     "fedora.backup_clean",
     {"keep_last": 3}, {}),

    ("BACKUP/backup_clean", "clean keep_last 5",
     "purge les backups en conservant les 5 plus recents",
     "fedora.backup_clean",
     {"keep_last": 5}, {}),

]


def tool_matches(result_tool, expected_tool):
    if expected_tool is None:
        return result_tool is None
    if result_tool is None:
        return False
    r = result_tool.split(".")[-1] if "." in result_tool else result_tool
    e = expected_tool.split(".")[-1] if "." in expected_tool else expected_tool
    return r == e


def check_args(result_args, mandatory):
    """Verifie les arguments. Retourne (missing, wrong)."""
    if result_args is None:
        result_args = {}
    missing = []
    wrong = []
    for k, v in mandatory.items():
        rv = result_args.get(k)
        if rv is None:
            missing.append(k)
        elif v != "" and str(rv).lower() != str(v).lower():
            wrong.append(f"{k}={v}(got={rv})")
    return missing, wrong


def run_opts_tests():
    G = "\033[32m"
    Y = "\033[33m"
    R = "\033[31m"
    C = "\033[36m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"

    print(f"\n{BOLD}{'='*70}{RESET}")
    print(f"{BOLD}  CAMPAGNE PARAMS AVANCES - EPHAISTOS (Qwen 7B){RESET}")
    print(f"{BOLD}{'='*70}{RESET}")
    print(f"  {DIM}Teste l'extraction des args optionnels via RAG + EPHAISTOS{RESET}\n")

    print(f"{C}[INIT]{RESET} Chargement du pipeline RAG...")
    t0 = time.time()
    config = RAGConfig.from_yaml(Path(__file__).parent.parent / "config.yaml")
    pipeline = Pipeline(config)
    pipeline.initialize()
    print(f"{G}[INIT]{RESET} Pipeline pret ({time.time()-t0:.1f}s)\n")

    results = []
    categories = {}

    for i, (cat, desc, query, expected_tool, mandatory_args, _) in enumerate(TESTS_OPTS, 1):
        label = query[:60] + "..." if len(query) > 60 else query
        print(f"{DIM}[{i:02d}/{len(TESTS_OPTS)}] {desc}{RESET}")
        print(f"  {DIM}>> {label}{RESET}")

        t_start = time.time()
        try:
            fused = pipeline._retrieve_specs(query)
            specs = [r.document for r in fused] if fused else []

            if not specs:
                result_tool = None
                result_args = {}
            else:
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

        tool_ok = tool_matches(result_tool, expected_tool)
        missing, wrong = check_args(result_args, mandatory_args)

        if result_tool is None or not tool_ok:
            status = "FAIL"
        elif missing or wrong:
            status = "PARTIAL"
        else:
            status = "PASS"

        color = G if status == "PASS" else (Y if status == "PARTIAL" else R)
        tool_str = (result_tool or "NONE").split(".")[-1][:18].ljust(19)
        detail = ""
        if not tool_ok and result_tool:
            exp = (expected_tool or "").split(".")[-1]
            got = (result_tool or "NONE").split(".")[-1]
            detail = f" {R}outil={got} attendu={exp}{RESET}"
        elif missing:
            detail = f" {Y}MANQUANT={missing}{RESET}"
        elif wrong:
            detail = f" {R}ERREUR={wrong}{RESET}"
        else:
            found_opts = {k: result_args[k] for k in mandatory_args if k in result_args}
            detail = f" {G}{found_opts}{RESET}"

        print(f"  {color}[{status:<7}]{RESET} -> {tool_str}{detail} {DIM}({elapsed:.1f}s){RESET}\n")

        entry = {
            "cat": cat, "desc": desc, "query": query,
            "expected_tool": expected_tool, "result_tool": result_tool,
            "result_args": result_args, "mandatory_args": mandatory_args,
            "missing": missing, "wrong": wrong,
            "status": status, "elapsed": elapsed
        }
        results.append(entry)
        categories.setdefault(cat.split("/")[0], []).append(entry)

    # Scores par categorie
    print(f"\n{BOLD}{'='*70}{RESET}")
    print(f"{BOLD}  SCORES PAR CATEGORIE{RESET}")
    print(f"{BOLD}{'='*70}{RESET}")

    total_pass = total_partial = total_fail = 0
    for cat_name, entries in sorted(categories.items()):
        n = len(entries)
        p = sum(1 for e in entries if e["status"] == "PASS")
        pa = sum(1 for e in entries if e["status"] == "PARTIAL")
        f = sum(1 for e in entries if e["status"] == "FAIL")
        total_pass += p
        total_partial += pa
        total_fail += f
        score_pct = round(100 * (p + 0.5 * pa) / n) if n else 0
        bar = f"{G}{'#' * p}{Y}{'~' * pa}{R}{'-' * f}{RESET}"
        print(f"  {BOLD}{cat_name:<8}{RESET} {bar} "
              f"{G}{p}P{RESET} {Y}{pa}~{RESET} {R}{f}F{RESET} / {n}  [{score_pct}%]")

    total = len(results)
    score_final = round(100 * (total_pass + 0.5 * total_partial) / total) if total else 0

    print(f"\n{BOLD}{'='*70}{RESET}")
    print(f"{BOLD}  SCORE FINAL PARAMS : "
          f"{G}{total_pass}{RESET}{BOLD} PASS  "
          f"{Y}{total_partial}{RESET}{BOLD} PARTIAL  "
          f"{R}{total_fail}{RESET}{BOLD} FAIL  / {total} tests{RESET}")
    print(f"{BOLD}  POURCENTAGE : {score_final}%{RESET}")
    print(f"  {DIM}(PASS=1pt, PARTIAL=0.5pt arg present mais valeur differente, FAIL=0pt){RESET}\n")

    # Details des echecs
    fails = [e for e in results if e["status"] in ("PARTIAL", "FAIL")]
    if fails:
        print(f"{BOLD}--- Cas a ameliorer ({len(fails)}) ---{RESET}")
        for e in fails:
            color = Y if e["status"] == "PARTIAL" else R
            print(f"  {color}[{e['status']}]{RESET} {e['desc']}")
            print(f"    Requete : {e['query']}")
            print(f"    Outil   : {e['result_tool']} (attendu: {e['expected_tool']})")
            print(f"    Args    : {e['result_args']}")
            if e["missing"]:
                print(f"    Manquant: {e['missing']}")
            if e["wrong"]:
                print(f"    Erreur  : {e['wrong']}")

    # Rapport texte
    report_path = Path(__file__).parent / "test_campaign_opts_report.txt"
    with open(report_path, "w") as f:
        f.write("CAMPAGNE PARAMS AVANCES - EPHAISTOS\n")
        f.write("=" * 70 + "\n\n")
        for r in results:
            f.write(f"[{r['status']:<7}] {r['desc']}\n")
            f.write(f"  Requete  : \"{r['query']}\"\n")
            f.write(f"  Attendu  : {r['expected_tool']} + {r['mandatory_args']}\n")
            f.write(f"  Outil    : {r['result_tool']}\n")
            f.write(f"  Args     : {r['result_args']}\n")
            if r["missing"]:
                f.write(f"  MANQUANT : {r['missing']}\n")
            if r["wrong"]:
                f.write(f"  ERREUR   : {r['wrong']}\n")
            f.write("\n")
        f.write("=" * 70 + "\n")
        f.write(f"PASS: {total_pass}  PARTIAL: {total_partial}  FAIL: {total_fail}\n")
        f.write(f"SCORE: {score_final}%\n")

    print(f"\nRapport sauvegarde : {report_path}")
    return results, categories, score_final


if __name__ == "__main__":
    run_opts_tests()
