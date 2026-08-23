"""Menu de selection des MCPs (deux colonnes : liste + description).

Porte de install-lyra-interactive.py (_render_mcp_menu + _phase_select_mcps),
alimente par le catalogue declaratif (load_catalog) : plus de _ALL_MCPS en
dur, la couleur et la description viennent de McpDef.
"""
from __future__ import annotations

import time

from rich.align import Align
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from installer.core.catalog import McpDef

from .keys import KEY_DOWN, KEY_ENTER, KEY_SPACE, KEY_UP, cbreak_mode, read_key
from .popup import popup_header
from .theme import DIM, GOLD, GOOD, TITLE, TITLE_DIM


def _describe(mcp: McpDef) -> Text:
    """Panneau droit : long_desc + exemples vocaux + notes en dim."""
    t = Text()
    t.append(mcp.long_desc, style="white")
    if mcp.examples:
        t.append("\n\n")
        for i, example in enumerate(mcp.examples):
            if i:
                t.append("\n")
            t.append(f'  "{example}"', style=f"bold {mcp.color}")
    if mcp.notes:
        t.append("\n\n")
        t.append(mcp.notes, style=DIM)
    return t


def render_menu(catalog: tuple[McpDef, ...], cursor: int,
                checked: dict[str, bool]) -> Table:
    """Rendu du menu de selection MCPs : liste gauche + description droite."""
    n_checked = sum(checked.values())

    # Colonne gauche : liste avec curseur
    left = Text()
    left.append("\n")
    for i, m in enumerate(catalog):
        mark = "[x]" if checked[m.id] else "[ ]"
        if i == cursor:
            left.append(f"  {mark} {m.name:<20}", style=f"bold {GOLD} reverse")
            left.append("\n")
        elif checked[m.id]:
            left.append(f"  {mark} {m.name:<20}\n", style=GOOD)
        else:
            left.append(f"  {mark} {m.name:<20}\n", style=DIM)

    left.append("\n")
    left.append(f"  {n_checked} selectionne(s)\n",
                style=GOOD if n_checked else DIM)
    left.append("\n")
    left.append("  [UP]/[DOWN]  naviguer\n", style=DIM)
    left.append("  [ESPACE]     cocher\n", style=DIM)
    left.append("  [ENTREE]     valider\n", style=DIM)
    left.append("  [A]          tout cocher\n", style=DIM)

    # Colonne droite : description de l'item sous le curseur
    current = catalog[cursor]
    right = Panel(
        _describe(current),
        title=f"[bold {current.color}]{current.name}[/]",
        subtitle=f"[{DIM}]{current.short_desc}[/]",
        style=f"dim {current.color}",
        padding=(1, 2),
        expand=True,
    )

    outer = Table.grid(expand=True)
    outer.add_column()
    header = Text("  QUELS MCPs CONNECTER A LYRA ?  ", style=TITLE)
    outer.add_row(Align.center(header))
    outer.add_row(Rule(style=TITLE_DIM))

    inner = Table.grid(expand=True, padding=(0, 1))
    inner.add_column(ratio=2, min_width=28)
    inner.add_column(ratio=3)
    inner.add_row(left, right)
    outer.add_row(inner)

    return outer


def _demo_select(console: Console, catalog: tuple[McpDef, ...]) -> list[str]:
    """Mode demo : tout cocher automatiquement apres ~1s."""
    console.clear()
    popup_header(console, "QUELS MCPs CONNECTER A LYRA ?", GOLD)
    console.print("  [dim yellow][DEMO] Tous les MCPs selectionnes "
                  "automatiquement.[/dim yellow]")
    console.print()
    for m in catalog:
        console.print(f"  [{GOOD}]\\[x][/] [bold]{m.name:<20}[/]  {m.short_desc}")
    time.sleep(1.2)
    return [m.id for m in catalog]


def select_mcps(console: Console, catalog: tuple[McpDef, ...],
                demo: bool = False) -> list[str]:
    """Menu interactif ; retourne les ids coches. Defaut = default_checked."""
    if demo:
        return _demo_select(console, catalog)

    import sys
    if not sys.stdin.isatty():
        # Pas de TTY : selection par defaut, sans interaction
        return [m.id for m in catalog if m.default_checked]

    cursor = 0
    checked = {m.id: m.default_checked for m in catalog}

    with cbreak_mode():
        console.clear()
        with Live(render_menu(catalog, cursor, checked), console=console,
                  refresh_per_second=20, screen=False) as live:
            while True:
                key = read_key(timeout=0.05)
                if key is None:
                    continue
                if key == KEY_UP:
                    cursor = (cursor - 1) % len(catalog)
                elif key == KEY_DOWN:
                    cursor = (cursor + 1) % len(catalog)
                elif key == KEY_SPACE:
                    mcp_id = catalog[cursor].id
                    checked[mcp_id] = not checked[mcp_id]
                elif key in KEY_ENTER:
                    break
                elif key in ("a", "A"):
                    all_on = all(checked.values())
                    for k in checked:
                        checked[k] = not all_on
                live.update(render_menu(catalog, cursor, checked))

    selected = [m.id for m in catalog if checked[m.id]]

    console.clear()
    popup_header(console, "MCPs SELECTIONNES", GOLD)
    for m in catalog:
        if checked[m.id]:
            console.print(f"  [{GOOD}]\\[+][/] [bold]{m.name}[/]  "
                          f"[{DIM}]{m.short_desc}[/]")
    time.sleep(0.8)
    return selected
