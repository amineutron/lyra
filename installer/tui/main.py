"""Orchestration du frontal TUI de l'installeur Lyra.

Flux : boot -> selection MCPs -> config devices -> recap + confirmation ->
pipeline core dans un thread + boucle Live (rendu model + mascotte,
traitement des Ask via popups) -> ecran final.
"""
from __future__ import annotations

import argparse
import queue
import sys
import threading
import time
from pathlib import Path
from typing import Optional, Sequence

from rich.console import Console
from rich.live import Live
from rich.prompt import Confirm
from rich.rule import Rule
from rich.table import Table

from installer.core.catalog import McpDef, load_catalog
from installer.core.events import Ask, AskBroker
from installer.core.osdetect import detect_current
from installer.core.pipeline import build_pipeline, run_pipeline
from installer.core.state import DEFAULT_LYRA_REPO, InstallState
from installer.core.sudoprime import ensure_sudo_cached

from . import boot, forms, menu, mode_select
from .mascot import MascotAnimator, pick_mascot
from .model import UIModel
from .popup import PopupPause, popup_header
from .render import build_node_meta, render_screen
from .theme import BAD, DIM, GOLD, GOOD, TEXT, TITLE, load_mascots, mascot_color


def _default_lyra_dir() -> Path:
    """Racine du clone lyra courant si on est dedans, sinon ~/lyra."""
    here = Path.cwd().resolve()
    for candidate in (here, *here.parents):
        if (candidate / "main_rag.py").exists() and (candidate / "lyra").is_dir():
            return candidate
    return Path.home() / "lyra"


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="installer.tui",
                                description="Installateur Lyra interactif")
    p.add_argument("--demo", action="store_true",
                   help="Simule l'installation (aucune action reelle)")
    p.add_argument("--repo", default=DEFAULT_LYRA_REPO)
    p.add_argument("--lyra-dir", type=Path, default=None)
    p.add_argument("--ollama-host", default="")
    p.add_argument("--skip-models", action="store_true")
    return p.parse_args(argv)


def _recap_and_confirm(console: Console, state: InstallState,
                       selected: tuple[McpDef, ...]) -> bool:
    console.clear()
    popup_header(console, "PRET A INSTALLER", GOLD)
    names = ", ".join(m.name for m in selected) or "aucun"
    models = "skip" if state.skip_models else "qwen:0.5b + llama:1b"
    console.print(f"  Repertoire  : [{TITLE}]{state.lyra_dir}[/]")
    console.print(f"  MCPs        : {names}")
    console.print(f"  Modeles LLM : {models}")
    console.print()
    if state.demo:
        console.print("  [dim yellow][DEMO] Confirmation automatique.[/dim yellow]")
        time.sleep(0.6)
        return True
    return Confirm.ask(f"  [{GOOD}]Lancer l'installation ?[/]",
                       default=True, console=console)


def _answer_ask(popup: PopupPause, ask: Ask):
    """Repond a un Ask du pipeline dans un popup (Live en pause)."""
    if ask.kind == "confirm":
        return popup.confirm(ask.prompt, default=bool(ask.default))
    if ask.kind == "input":
        return popup.ask(ask.prompt, default=str(ask.default or ""))
    # kind inconnu (ex: countdown) : afficher le prompt et confirmer
    popup.print(f"  [{TITLE}]{ask.prompt}[/]")
    return popup.confirm("Continuer ?", default=True)


def _mascot_state(snap) -> str:
    if snap.done:
        return "ok" if snap.ok else "err"
    if any(s.status == "run" for s in snap.steps):
        return "work"
    return "busy"


def _run_install(console: Console, state: InstallState,
                 selected: tuple[McpDef, ...],
                 mascot: Optional[MascotAnimator]) -> tuple[bool, str]:
    """Thread pipeline + boucle Live 10fps. Retourne (succes, erreur)."""
    pipeline = build_pipeline(state, selected)
    model = UIModel(pipeline)
    broker = AskBroker(emit=model.handle_event)
    node_meta = build_node_meta(selected)

    worker = threading.Thread(
        target=run_pipeline,
        args=(state, selected, model.handle_event, broker),
        kwargs={"pipeline": pipeline},
        daemon=True,
    )

    t0 = time.monotonic()
    tick = 0
    worker.start()
    console.clear()

    def frame():
        snap = model.snapshot()
        mtext, mstyle, mname = "", DIM, ""
        if mascot is not None:
            mtext = mascot.next_frame(_mascot_state(snap))
            mstyle = f"bold {mascot_color(mascot.color_code)}"
            mname = mascot.name
        return snap, render_screen(
            snap, tick, demo=state.demo, t0=t0, node_meta=node_meta,
            mascot_text=mtext, mascot_style=mstyle, mascot_name=mname)

    snap, screen = frame()
    with Live(screen, console=console, refresh_per_second=10) as live:
        while True:
            tick += 1
            try:
                ask = model.asks.get_nowait()
            except queue.Empty:
                ask = None
            if ask is not None:
                with PopupPause(live, console, title=ask.prompt) as popup:
                    answer = _answer_ask(popup, ask)
                broker.answer(ask.ask_id, answer)
            snap, screen = frame()
            live.update(screen)
            if snap.done:
                break
            time.sleep(0.1)

    worker.join(timeout=5)
    return snap.ok, snap.error


def _final_screen(console: Console, state: InstallState,
                  selected: tuple[McpDef, ...], ok: bool, error: str) -> None:
    console.print()
    if not ok:
        console.print(Rule(f"[{BAD}]INSTALLATION ECHOUEE[/]", style=BAD))
        console.print()
        console.print(f"  [{BAD}]{error or 'erreur inconnue'}[/]")
        console.print()
        return

    console.print(Rule(f"[{GOOD}]LYRA INSTALLE AVEC SUCCES[/]", style=GOOD))
    console.print()

    t = Table(show_header=True, header_style=TITLE, box=None, padding=(0, 2))
    t.add_column("MCP", style=TEXT)
    t.add_column("Statut", style=GOOD)
    t.add_column("Config", style=DIM)
    for mcp in selected:
        values = state.device_config.get(mcp.id, {})
        summary = "  ".join(
            f"{k}={'***' if any(f.key == k and f.secret for f in mcp.fields) else v}"
            for k, v in values.items()
        ) or ("local" if not mcp.installable else "-")
        t.add_row(mcp.name, "[+] OK", summary)
    console.print(t)

    console.print()
    console.print(Rule(style=GOOD))
    console.print()
    console.print(f"  Pour lancer Lyra : [{TITLE}]lyra[/]")
    console.print(f"  Logs du demon    : [{DIM}]journalctl --user -u "
                  f"lyra-daemon -f[/]")
    console.print()


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    console = Console()

    # Phase 1 : boot
    boot.run_boot(console)

    # Phase 1.5 : choix du mode (terminal par defaut, bascule app possible)
    mascot = pick_mascot(load_mascots())
    if mode_select.select_mode(console, demo=args.demo,
                               mascot=mascot) == mode_select.MODE_APP:
        # Le processus devient le serveur de l'app graphique (memes args)
        cmd = [sys.executable, "-m", "installer.app"]
        if args.demo:
            cmd.append("--demo")
        import os
        os.execv(sys.executable, cmd)

    # Phase 2 : selection MCPs
    catalog = load_catalog()
    selected_ids = menu.select_mcps(console, catalog, demo=args.demo)
    selected = tuple(m for m in catalog if m.id in set(selected_ids))
    if not selected:
        console.print(f"\n  [{DIM}]Aucun MCP selectionne. Installation de "
                      f"Lyra core uniquement.[/]")
        time.sleep(1)

    # Phase 3 : config devices
    device_config = forms.collect_device_config(console, selected,
                                                demo=args.demo)

    # Etat d'installation
    state = InstallState(
        distro=detect_current(),
        lyra_dir=(args.lyra_dir or _default_lyra_dir()).expanduser(),
        repo_url=args.repo,
        selected_mcps=tuple(m.id for m in selected),
        device_config=device_config,
        ollama_host=args.ollama_host,
        skip_models=args.skip_models,
        demo=args.demo,
    )

    # Recap + confirmation
    if not _recap_and_confirm(console, state, selected):
        console.print(f"  [{DIM}]Installation annulee.[/]")
        return 0

    # Amorce sudo AVANT Rich Live : le pipeline tourne ensuite dans un
    # thread arriere-plan sans terminal interactif pour un mot de passe.
    if not args.demo:
        console.print(f"\n  [{DIM}]Mot de passe sudo (paquets systeme, "
                      f"regles NOPASSWD)...[/]")
        if not ensure_sudo_cached(demo=args.demo):
            console.print(f"\n  [{BAD}]Mot de passe sudo requis pour "
                          f"installer.[/]")
            return 1

    # Phase 4 : installation animee (meme mascotte que le choix de mode)
    ok, error = _run_install(console, state, selected, mascot)

    # Phase 5 : ecran final
    _final_screen(console, state, selected, ok, error)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
