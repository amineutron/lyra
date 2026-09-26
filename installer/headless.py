"""Installeur Lyra sans interface (roadmap #44) : meme pipeline que la TUI,
chaque question recoit sa valeur par defaut, la sortie est du texte brut.

Pour les tests d'installation automatiques (tests/installer/vm_install_test.sh)
et les machines sans terminal interactif. Aucun MCP par defaut : --mcps les
ajoute par identifiant du catalogue (champs d'appareil laisses vides).

    ./installer/install.sh --headless --ollama-host 192.0.2.1
    ./installer/install.sh --headless --demo          # simulation, aucune commande
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable, Optional, Sequence

from installer.core.catalog import load_catalog
from installer.core.events import Ask, AskBroker, Output, StepChange
from installer.core.osdetect import detect_current
from installer.core.pipeline import run_pipeline
from installer.core.state import DEFAULT_LYRA_REPO, InstallState
from installer.core.sudoprime import ensure_sudo_cached


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="installer.headless", description="Installeur Lyra sans interface")
    p.add_argument("--demo", action="store_true", help="simule l'installation (aucune action reelle)")
    p.add_argument("--repo", default=DEFAULT_LYRA_REPO)
    p.add_argument("--lyra-dir", type=Path, default=None)
    p.add_argument("--ollama-host", default="")
    p.add_argument("--skip-models", action="store_true")
    p.add_argument("--mcps", default="", help="identifiants du catalogue, separes par des virgules")
    return p.parse_args(argv)


def select_mcps(catalog, ids: str):
    """MCP demandes, dans l'ordre du catalogue ; un identifiant inconnu est une erreur."""
    wanted = [i.strip() for i in ids.split(",") if i.strip()]
    known = {m.id for m in catalog}
    unknown = [i for i in wanted if i not in known]
    if unknown:
        raise SystemExit(f"MCP inconnu(s) : {', '.join(unknown)} (catalogue : {', '.join(sorted(known))})")
    return tuple(m for m in catalog if m.id in set(wanted))


def make_emit(out: Callable[[str], None], broker_ref: list) -> Callable[[object], None]:
    """Emetteur texte : les etapes et la sortie des commandes ; toute question
    recoit sa valeur par defaut (journalisee pour le rapport)."""
    def emit(event: object) -> None:
        if isinstance(event, StepChange):
            detail = f" : {event.detail}" if event.detail else ""
            out(f"[{event.status}] {event.step_id}{detail}")
        elif isinstance(event, Output):
            out(f"    {event.line}")
        elif isinstance(event, Ask):
            out(f"[auto] {event.prompt} -> {event.default!r}")
            broker_ref[0].answer(event.ask_id, event.default)
    return emit


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    selected = select_mcps(load_catalog(), args.mcps)
    from installer.tui.main import _default_lyra_dir  # meme racine par defaut que la TUI
    state = InstallState(
        distro=detect_current(),
        lyra_dir=(args.lyra_dir or _default_lyra_dir()).expanduser(),
        repo_url=args.repo,
        selected_mcps=tuple(m.id for m in selected),
        ollama_host=args.ollama_host,
        skip_models=args.skip_models,
        demo=args.demo,
    )
    if not args.demo and not ensure_sudo_cached(demo=False):
        print("[err] sudo requis (paquets systeme, regles NOPASSWD)", file=sys.stderr)
        return 1
    broker_ref: list = []
    emit = make_emit(lambda line: print(line, flush=True), broker_ref)
    broker_ref.append(AskBroker(emit=emit))
    ok = run_pipeline(state, selected, emit, broker_ref[0])
    print("INSTALLATION OK" if ok else "INSTALLATION ECHOUEE", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
