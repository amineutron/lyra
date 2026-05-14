#!/usr/bin/env python3
"""
Script de lancement de la scene Iron Man.

Usage:
    cd /home/amineutron/dev/lyra
    source .venv/bin/activate

    python -m scenes.ironman.run_scene              # Scene complete (~33s)
    python -m scenes.ironman.run_scene --test       # Validation seulement
    python -m scenes.ironman.run_scene --phase 1    # Test phase specifique
    python -m scenes.ironman.run_scene --phase 2
    python -m scenes.ironman.run_scene --phase 3    # Pulsations (12s)
"""

import logging
import sys
import argparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scenes.ironman import IronManOrchestrator
from scenes.ironman.phases import (
    Phase0Detection, Phase1Blackout, Phase2Impact,
    Phase3Buildup, Phase4Transition, Phase5TTS
)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)


def run_single_phase(phase_num: int):
    """Execute une seule phase pour test."""
    phases = {
        0: ("Validation", Phase0Detection),
        1: ("Blackout", Phase1Blackout),
        2: ("Impact", Phase2Impact),
        3: ("Buildup", Phase3Buildup),
        4: ("Transition", Phase4Transition),
        5: ("TTS", Phase5TTS),
    }

    if phase_num not in phases:
        print(f"Phase {phase_num} invalide (0-5)")
        return

    name, PhaseClass = phases[phase_num]
    print(f"\n\033[1;36m=== TEST PHASE {phase_num}: {name.upper()} ===\033[0m\n")

    phase = PhaseClass()

    if phase_num == 0:
        success, msg, state = phase.validate_and_prepare()
        print(f"Resultat: {'OK' if success else 'ECHEC'} - {msg}")
        if state:
            print(f"  TV: {state.get('tv', {}).get('power', 'unknown')}")
            print(f"  Hue: {len(state.get('hue', {}).get('lights', {}))} lumieres")
    else:
        result = phase.execute()
        print(f"Resultat: {result}")


def run_full_scene():
    """Execute la scene complete via l'orchestrateur."""
    print("\n\033[1;36m" + "="*60 + "\033[0m")
    print("\033[1;36m   IRON MAN SCENE - Experience Complete (~33s)\033[0m")
    print("\033[1;36m" + "="*60 + "\033[0m")
    print("\nCe script va lancer la scene complete:")
    print("  1. Validation devices")
    print("  2. Blackout (3s)")
    print("  3. Flash + YouTube AC/DC")
    print("  4. Pulsations (12s)")
    print("  5. Transition (7s)")
    print("  6. Voix J.A.R.V.I.S.")
    print("\n\033[33mAssurez-vous que:\033[0m")
    print("  - TV Philips accessible (192.168.1.50)")
    print("  - Bridge Hue accessible (192.168.1.51)")
    print("  - Volume TV raisonnable!")
    print("\n" + "-"*60)

    response = input("\n\033[1mLancer la scene? [o/N]\033[0m ").strip().lower()
    if response not in ('o', 'oui', 'y', 'yes'):
        print("Annule.")
        return

    print("\n\033[1;33m🦸 Lancement de la scene Iron Man...\033[0m\n")

    orchestrator = IronManOrchestrator()
    result = orchestrator.trigger("je suis iron man")

    if result:
        print("\n\033[1;32m" + "="*60 + "\033[0m")
        print("\033[1;32m   SCENE TERMINEE!\033[0m")
        print("\033[1;32m" + "="*60 + "\033[0m")

        status = orchestrator.get_status()
        print(f"\nEtat final: \033[1m{status['state']}\033[0m")

        if status['phase_results']:
            print("\nResultats par phase:")
            for phase, res in status['phase_results'].items():
                success = res.get('success', False)
                duration = res.get('duration', 0)
                icon = "\033[32m✓\033[0m" if success else "\033[31m✗\033[0m"
                print(f"  {icon} {phase}: {duration:.1f}s")
    else:
        print("\033[31mErreur: Scene non lancee\033[0m")


def main():
    parser = argparse.ArgumentParser(description="Scene Iron Man")
    parser.add_argument("--test", action="store_true",
                        help="Test validation seulement")
    parser.add_argument("--phase", type=int, choices=[0, 1, 2, 3, 4, 5],
                        help="Tester une phase specifique (0-5)")
    args = parser.parse_args()

    if args.test:
        run_single_phase(0)
    elif args.phase is not None:
        run_single_phase(args.phase)
    else:
        run_full_scene()


if __name__ == "__main__":
    main()
