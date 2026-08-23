"""Popups par-dessus le Live (pause du rendu, prompt, reprise).

Porte de install-lyra-interactive.py (PopupPause) ; la methode checklist
(code mort) a ete supprimee. Le style par defaut passe du cyan a la
palette neutroncore.
"""
from __future__ import annotations

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from .theme import GOLD


class PopupPause:
    """Context manager : met en pause le Live, affiche un popup, reprend."""

    def __init__(self, live: Live, console: Console,
                 title: str, style: str = GOLD):
        self._live = live
        self._console = console
        self._title = title
        self._style = style

    def __enter__(self) -> "PopupPause":
        self._live.stop()
        self._console.clear()
        self._console.print()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._console.print()
        self._live.start()

    def print(self, *args: object, **kwargs: object) -> None:
        self._console.print(*args, **kwargs)

    def ask(self, prompt: str, default: str = "",
            password: bool = False) -> str:
        return Prompt.ask(
            f"  [bold {self._style}]{prompt}[/]",
            default=default,
            password=password,
            console=self._console,
        )

    def confirm(self, prompt: str, default: bool = True) -> bool:
        return Confirm.ask(
            f"  [bold {self._style}]{prompt}[/]",
            default=default,
            console=self._console,
        )


def popup_header(console: Console, title: str, style: str = GOLD) -> None:
    """En-tete de popup plein ecran (hors Live)."""
    console.print()
    console.print(Panel(
        f"[bold {style}]{title}[/]",
        style=style,
        expand=False,
        padding=(0, 4),
    ))
    console.print()
