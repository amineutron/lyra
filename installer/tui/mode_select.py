"""Ecran de choix du mode d'installation : terminal (defaut) ou app web.

Affiche juste apres le boot : menu 2 options aux fleches, mascotte animee,
palette or/rose. En --demo ou hors TTY : reste en mode terminal sans
interaction (le parcours --demo doit rester 100% automatique).
"""
from __future__ import annotations

import sys
import time
from typing import Optional

from rich.align import Align
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from .keys import KEY_DOWN, KEY_ENTER, KEY_UP, cbreak_mode, read_key
from .mascot import MascotAnimator
from .theme import DIM, GOLD, MUTED, ROSE, RUN, TITLE, mascot_color

MODE_TUI = "tui"
MODE_APP = "app"

_OPTIONS = (
    (MODE_TUI, "Terminal",
     "Installation dans ce terminal (menu fleches, pipeline anime)."),
    (MODE_APP, "Application",
     "Ouvre l'installeur graphique dans le navigateur (127.0.0.1:9877)."),
)


def _render(cursor: int, tick: int,
            mascot: Optional[MascotAnimator]) -> Table:
    grid = Table.grid(expand=True)
    grid.add_column()

    title = Text()
    for ch in "M O D E   D ' I N S T A L L A T I O N":
        title.append(ch, style=TITLE if ch not in " '" else f"dim {GOLD}")
    grid.add_row(Align.center(title))
    grid.add_row(Rule(style=f"dim {GOLD}"))
    grid.add_row(Text(""))

    inner = Table.grid(expand=True, padding=(0, 2))
    inner.add_column(ratio=3)
    inner.add_column(ratio=1)

    left = Text()
    for i, (_, label, desc) in enumerate(_OPTIONS):
        is_cursor = (i == cursor)
        marker = ">" if is_cursor else " "
        style = f"bold {ROSE} reverse" if is_cursor else f"bold {MUTED}"
        left.append(f"\n  {marker} {label:<14}", style=style)
        left.append("\n")
        left.append(f"      {desc}\n", style=DIM if not is_cursor else "white")
    left.append("\n")
    left.append("  [UP]/[DOWN]  choisir     [ENTREE]  valider\n", style=DIM)

    right = Text("")
    if mascot is not None:
        right = Text(mascot.next_frame("idle" if tick % 2 else "busy"),
                     style=f"bold {mascot_color(mascot.color_code)}")

    inner.add_row(left, Align.center(
        Panel(right, style=f"dim {GOLD}", padding=(0, 1), expand=False)
        if mascot is not None else Text("")))
    grid.add_row(inner)
    grid.add_row(Rule(style=f"dim {GOLD}"))
    return grid


def select_mode(console: Console, *, demo: bool,
                mascot: Optional[MascotAnimator] = None) -> str:
    """Retourne MODE_TUI ou MODE_APP. Sans TTY ou en demo : MODE_TUI."""
    if demo or not sys.stdin.isatty():
        return MODE_TUI

    cursor = 0
    console.clear()
    with cbreak_mode():
        with Live(_render(cursor, 0, mascot), console=console,
                  refresh_per_second=10, screen=False) as live:
            tick = 0
            while True:
                key = read_key(timeout=0.1)
                tick += 1
                if key == KEY_UP:
                    cursor = (cursor - 1) % len(_OPTIONS)
                elif key == KEY_DOWN:
                    cursor = (cursor + 1) % len(_OPTIONS)
                elif key in KEY_ENTER:
                    break
                live.update(_render(cursor, tick, mascot))

    mode = _OPTIONS[cursor][0]
    if mode == MODE_APP:
        console.print()
        console.print(f"  [{RUN}]Lancement de l'installeur graphique...[/]")
        console.print(f"  [{DIM}]http://127.0.0.1:9877/ui/ — ce terminal "
                      f"devient le serveur (Ctrl+C pour arreter).[/]")
        time.sleep(1.0)
    return mode
