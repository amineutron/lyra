"""Rendu de l'ecran d'installation (Live).

Porte de install-lyra-interactive.py (_render + _render_node_graph) :
- l'etat vient d'un Snapshot du UIModel (plus de globals) ;
- les couleurs des noeuds MCP viennent de McpDef.color (catalogue) ;
- palette neutroncore (GOLD accents, ROSE etape en cours) ;
- frise d'etapes numerotees en tete + panneau mascotte a droite.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from rich.align import Align
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from installer.core.catalog import McpDef

from .model import Snapshot, StepView
from .theme import (BAD, DIM, GOLD, GOOD, MUTED, ROSE, RUN, SPINNER_FRAMES,
                    TEXT, TITLE, TITLE_DIM, WARN)

_PIPE_COMPACT_THRESHOLD = 8


@dataclass(frozen=True)
class NodeMeta:
    label: str
    color: str


def build_node_meta(catalog: tuple[McpDef, ...]) -> dict[str, NodeMeta]:
    """Label + couleur de chaque noeud MCP, depuis le catalogue."""
    return {
        mcp.id: NodeMeta(label=mcp.id.upper()[:8], color=mcp.color)
        for mcp in catalog
    }


# ── Frise d'etapes (facon .pipe neutroncore) ─────────────────────────

def _pipe_style(step: StepView) -> str:
    if step.status in ("ok", "skip"):
        return f"bold {GOLD}"
    if step.status == "run":
        return f"bold {ROSE}"
    if step.status == "err":
        return BAD
    return MUTED


def render_pipe(steps: tuple[StepView, ...]) -> Text:
    """Ronds numerotes relies : ( 1 )--( 2 )--... (compact si > 8 etapes)."""
    compact = len(steps) > _PIPE_COMPACT_THRESHOLD
    t = Text("  ")
    for i, step in enumerate(steps):
        if i:
            t.append("--", style=MUTED)
        node = f"({i + 1})" if compact else f"( {i + 1} )"
        t.append(node, style=_pipe_style(step))
    return t


# ── Graphe ASCII des noeuds MCP ──────────────────────────────────────

def render_node_graph(nodes: tuple[str, ...],
                      node_meta: dict[str, NodeMeta], tick: int) -> Text:
    t = Text()

    if not nodes:
        t.append("          ╔══════════╗\n", style=TITLE_DIM)
        t.append("          ║  ", style=TITLE_DIM)
        t.append("◆ LYRA ◆", style=TITLE)
        t.append("  ║\n", style=TITLE_DIM)
        t.append("          ╚══════════╝\n", style=TITLE_DIM)
        t.append("          [en attente des MCPs...]\n", style=DIM)
        return t

    t.append("       ╔══════════╗\n", style=TITLE_DIM)
    t.append("       ║  ", style=TITLE_DIM)
    t.append("◆ LYRA ◆", style=TITLE)
    t.append("  ║\n", style=TITLE_DIM)
    t.append("       ╚═════╤════╝\n", style=TITLE_DIM)

    for i, node_id in enumerate(nodes):
        meta = node_meta.get(node_id, NodeMeta(node_id.upper()[:8], "white"))
        is_last = (i == len(nodes) - 1)
        prefix = "             └──" if is_last else "             ├──"
        blink = SPINNER_FRAMES[tick % len(SPINNER_FRAMES)] if is_last else "●"
        t.append(prefix, style=TITLE_DIM)
        t.append(f"[{blink}] ", style=f"bold {meta.color}")
        t.append(f"{meta.label}\n", style=f"bold {meta.color}")

    return t


# ── Panneau mascotte ─────────────────────────────────────────────────

def render_mascot(mascot_text: str, mascot_style: str, name: str) -> Panel:
    return Panel(
        Align.center(Text(mascot_text, style=mascot_style)),
        title=f"[{DIM}]{name}[/]",
        style=DIM,
        padding=(0, 1),
        expand=False,
    )


# ── Colonne des etapes ───────────────────────────────────────────────

def _render_steps(steps: tuple[StepView, ...], tick: int) -> Text:
    t = Text()
    for s in steps:
        if s.status == "ok":
            t.append("  [+] ", style=TITLE_DIM)
            t.append(f"{s.label:<28}", style=TEXT)
            t.append("OK", style=GOOD)
            t.append(f"  {s.elapsed:.1f}s\n", style=DIM)
        elif s.status == "run":
            sp = SPINNER_FRAMES[tick % len(SPINNER_FRAMES)]
            t.append(f"  {sp}  ", style=RUN)
            t.append(f"{s.label:<28}", style=TEXT)
            t.append(f"{s.detail[:20]}\n" if s.detail else "\n",
                     style=f"dim {ROSE}")
        elif s.status == "err":
            t.append("  [!] ", style=BAD)
            t.append(f"{s.label:<28}", style=BAD)
            t.append("ERREUR\n", style=BAD)
        elif s.status == "skip":
            t.append("  [-] ", style=DIM)
            t.append(f"{s.label}\n", style=DIM)
        else:
            t.append("  [ ] ", style=DIM)
            t.append(f"{s.label}\n", style=DIM)
    return t


# ── Ecran complet ────────────────────────────────────────────────────

def render_screen(snap: Snapshot, tick: int, *,
                  demo: bool, t0: float,
                  node_meta: dict[str, NodeMeta],
                  mascot_text: str = "",
                  mascot_style: str = DIM,
                  mascot_name: str = "") -> Table:
    grid = Table.grid(expand=True)
    grid.add_column()

    # En-tete
    title = Text()
    for ch in "L . Y . R . A":
        title.append(ch, style=TITLE if ch not in ". " else TITLE_DIM)
    grid.add_row(Align.center(title))
    subtitle = "SIMULATION (--demo)" if demo else "INSTALLATION EN COURS"
    grid.add_row(Align.center(Text(subtitle, style=f"dim {WARN}" if demo else DIM)))
    grid.add_row(render_pipe(snap.steps))
    grid.add_row(Rule(style=TITLE_DIM))
    grid.add_row(Text(""))

    # Deux colonnes : etapes | graphe + mascotte
    inner = Table.grid(expand=True, padding=(0, 2))
    inner.add_column(ratio=3)
    inner.add_column(ratio=2)

    right = Table.grid()
    right.add_column()
    right.add_row(render_node_graph(snap.nodes, node_meta, tick))
    if mascot_text:
        right.add_row(Text(""))
        right.add_row(render_mascot(mascot_text, mascot_style, mascot_name))

    inner.add_row(_render_steps(snap.steps, tick), right)
    grid.add_row(inner)

    if snap.error:
        grid.add_row(Rule(style=f"dim {BAD}"))
        grid.add_row(Text(f"  ECHEC : {snap.error}", style=BAD))

    # Logs
    grid.add_row(Text(""))
    grid.add_row(Rule(style=DIM, title=f"[{DIM}]sortie[/]"))
    for line in (snap.logs or ("initialisation...",)):
        t = Text("  ▌ ", style=TITLE_DIM)
        t.append(line[:110], style=DIM)
        grid.add_row(t)

    # Pied
    grid.add_row(Text(""))
    done_n = sum(1 for s in snap.steps if s.status in ("ok", "skip"))
    elapsed = time.monotonic() - t0
    foot = Text(f"  {done_n}/{len(snap.steps)} etapes", style=TITLE)
    foot.append(f"  ·  {elapsed:.0f}s", style=DIM)
    grid.add_row(foot)
    grid.add_row(Rule(style=TITLE_DIM))

    return grid
