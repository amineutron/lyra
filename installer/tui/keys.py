"""Lecture clavier raw (fleches, espace, entree).

Porte tel quel de install-lyra-interactive.py (_read_key) : os.read + select
pour bypasser le buffer TextIO de sys.stdin — indispensable pour lire les
sequences d'echappement des fleches (\\x1b[A/B). Necessite le mode cbreak.
"""
from __future__ import annotations

import contextlib
import os
import select
import sys
import termios
import tty
from typing import Iterator, Optional

KEY_UP = "\x1b[A"
KEY_DOWN = "\x1b[B"
KEY_SPACE = " "
KEY_ENTER = ("\r", "\n")


def read_key(timeout: float = 0.08) -> Optional[str]:
    """Lit une touche sans bloquer (timeout en secondes).

    Utilise os.read(fd) pour bypasser le buffer Python — indispensable
    pour lire les sequences d'echappement des fleches (\\x1b[A/B).
    Necessite que le terminal soit en mode cbreak (setcbreak).
    """
    if not sys.stdin.isatty():
        return None
    fd = sys.stdin.fileno()
    ready, _, _ = select.select([sys.stdin], [], [], timeout)
    if not ready:
        return None
    # os.read bypasse le buffer interne de sys.stdin
    ch = os.read(fd, 1).decode("latin-1")
    if ch == "\x1b":
        # Sequence ESC : lire [ puis A/B rapidement (delai court = 50ms)
        r2, _, _ = select.select([sys.stdin], [], [], 0.05)
        if r2:
            ch += os.read(fd, 1).decode("latin-1")
            r3, _, _ = select.select([sys.stdin], [], [], 0.05)
            if r3:
                ch += os.read(fd, 1).decode("latin-1")
    return ch


@contextlib.contextmanager
def cbreak_mode() -> Iterator[None]:
    """Passe le terminal en mode cbreak et restaure a la sortie."""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
