#!/usr/bin/env python3
"""
Script de lancement de la scene Iron Man.

Usage:
    cd /home/amineutron/dev/lyra
    source .venv/bin/activate

    python -m scenes.ironman.run_scene                  # Scene complete (~33s)
    python -m scenes.ironman.run_scene --test           # Validation seulement
    python -m scenes.ironman.run_scene --phase 1        # Une phase seule
    python -m scenes.ironman.run_scene --phases 2-4     # Plage de phases
    python -m scenes.ironman.run_scene --phases 1,3,5   # Liste de phases
    python -m scenes.ironman.run_scene --from-phase 3   # De la phase 3 a la fin
    python -m scenes.ironman.run_scene --phase 1 -y     # Sans confirmation

Notes sous-scenes:
    - La Phase 0 (validation + capture etat rollback) est prefixee
      automatiquement, sauf avec --no-validate.
    - L'etat Hue/TV est restaure a la fin, sauf avec --no-rollback.
    - Les ecrans PC eteints par la Phase 1 se rallument sur n'importe
      quelle touche (armee 1s apres extinction) ; en mode sous-scene un
      rallumage auto a 60s est arme en secours.
"""

import logging
import sys
import argparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scenes.ironman import IronManOrchestrator
from scenes.ironman.metrics import load_runs, format_comparison

# Rallumage auto des ecrans PC en mode test/sous-scene (secours)
TEST_PC_AUTO_WAKE_S = 60

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)

PHASE_NAMES = {
    0: "Validation",
    1: "Blackout",
    2: "Impact",
    3: "Buildup",
    4: "Transition",
    5: "TTS",
}


def parse_phase_selection(spec: str) -> list:
    """
    Parse une specification de phases: "3", "2-4", "1,3,5".

    Returns:
        Liste ordonnee de numeros de phases

    Raises:
        ValueError si la specification est invalide
    """
    phases = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            start, end = int(start_s), int(end_s)
            if start > end:
                raise ValueError(f"Plage inversee: {part}")
            phases.extend(range(start, end + 1))
        else:
            phases.append(int(part))

    seen = set()
    ordered = []
    for p in phases:
        if p not in PHASE_NAMES:
            raise ValueError(f"Phase invalide: {p} (0-5)")
        if p not in seen:
            seen.add(p)
            ordered.append(p)
    return ordered


def run_sub_scene(selection: list, rollback: bool = True,
                  validate_first: bool = True):
    """Execute une selection de phases via l'orchestrateur."""
    names = ", ".join(f"{n}-{PHASE_NAMES[n]}" for n in selection)
    print(f"\n\033[1;36m=== SOUS-SCENE: {names} ===\033[0m\n")

    orchestrator = IronManOrchestrator(pc_auto_wake_s=TEST_PC_AUTO_WAKE_S)
    result = orchestrator.run_phases(
        selection, rollback=rollback, validate_first=validate_first
    )

    print(f"\nSucces: {'OUI' if result['success'] else 'NON'}")
    print(f"Phases executees: {result['phases_run']}")
    for phase_key, res in result["phase_results"].items():
        ok = res.get("success", False)
        duration = res.get("duration", 0)
        mark = "\033[32m[OK]\033[0m" if ok else "\033[31m[KO]\033[0m"
        print(f"  {mark} {phase_key}: {duration:.1f}s")

    if 1 in result["phases_run"]:
        print("\n\033[33mEcrans PC eteints: appuie sur une touche pour les "
              f"rallumer (auto dans {TEST_PC_AUTO_WAKE_S}s)\033[0m")

    return result


def run_full_scene(skip_confirm: bool = False):
    """Execute la scene complete via l'orchestrateur."""
    print("\n\033[1;36m" + "=" * 60 + "\033[0m")
    print("\033[1;36m   IRON MAN SCENE - Experience Complete (~33s)\033[0m")
    print("\033[1;36m" + "=" * 60 + "\033[0m")
    print("\nCe script va lancer la scene complete:")
    print("  1. Validation devices")
    print("  2. Blackout (3s) + ecrans PC eteints")
    print("  3. Flash + YouTube AC/DC")
    print("  4. Pulsations (12s)")
    print("  5. Transition (7s)")
    print("  6. Voix J.A.R.V.I.S.")
    print("\n\033[33mAssurez-vous que:\033[0m")
    print("  - TV Philips accessible")
    print("  - Bridge Hue accessible")
    print("  - Volume TV raisonnable!")
    print("\n" + "-" * 60)

    if not skip_confirm:
        response = input("\n\033[1mLancer la scene? [o/N]\033[0m ").strip().lower()
        if response not in ('o', 'oui', 'y', 'yes'):
            print("Annule.")
            return

    print("\n\033[1;33mLancement de la scene Iron Man...\033[0m\n")

    orchestrator = IronManOrchestrator()
    result = orchestrator.trigger("je suis iron man")

    if result:
        print("\n\033[1;32m" + "=" * 60 + "\033[0m")
        print("\033[1;32m   SCENE TERMINEE!\033[0m")
        print("\033[1;32m" + "=" * 60 + "\033[0m")

        status = orchestrator.get_status()
        print(f"\nEtat final: \033[1m{status['state']}\033[0m")

        if status['phase_results']:
            print("\nResultats par phase:")
            for phase, res in status['phase_results'].items():
                success = res.get('success', False)
                duration = res.get('duration', 0)
                mark = "\033[32m[OK]\033[0m" if success else "\033[31m[KO]\033[0m"
                print(f"  {mark} {phase}: {duration:.1f}s")

        print("\n\033[33mEcrans PC eteints: appuie sur une touche pour les "
              "rallumer\033[0m")
    else:
        print("\033[31mErreur: Scene non lancee\033[0m")


def main():
    parser = argparse.ArgumentParser(description="Scene Iron Man")
    parser.add_argument("--test", action="store_true",
                        help="Test validation seulement (equivalent --phase 0)")
    parser.add_argument("--phase", type=int, choices=range(6),
                        help="Executer une phase specifique (0-5)")
    parser.add_argument("--phases", type=str,
                        help="Executer une selection: '2-4' ou '1,3,5'")
    parser.add_argument("--from-phase", type=int, choices=range(6),
                        dest="from_phase",
                        help="Executer de la phase N a la fin (N-5)")
    parser.add_argument("-y", "--yes", action="store_true",
                        help="Sauter la confirmation (scene complete)")
    parser.add_argument("--no-rollback", action="store_true",
                        help="Ne pas restaurer l'etat Hue/TV apres la sous-scene")
    parser.add_argument("--no-validate", action="store_true",
                        help="Ne pas prefixer la Phase 0 (pas d'etat rollback)")
    parser.add_argument("--metrics", action="store_true",
                        help="Afficher les metriques des 5 derniers runs")
    args = parser.parse_args()

    if args.metrics:
        print("\n\033[1;36m=== METRIQUES - 5 DERNIERS RUNS ===\033[0m\n")
        print(format_comparison(load_runs()))
        return

    exclusive = [args.test, args.phase is not None,
                 args.phases is not None, args.from_phase is not None]
    if sum(exclusive) > 1:
        parser.error("--test, --phase, --phases et --from-phase sont exclusifs")

    if args.test:
        selection = [0]
    elif args.phase is not None:
        selection = [args.phase]
    elif args.phases is not None:
        try:
            selection = parse_phase_selection(args.phases)
        except ValueError as e:
            parser.error(str(e))
    elif args.from_phase is not None:
        selection = list(range(args.from_phase, 6))
    else:
        run_full_scene(skip_confirm=args.yes)
        return

    run_sub_scene(
        selection,
        rollback=not args.no_rollback,
        validate_first=not args.no_validate,
    )


if __name__ == "__main__":
    main()
