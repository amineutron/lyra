"""Phase de boot : ASCII art LYRA + boot log facon BootSplash neutroncore.

Art porte tel quel de install-lyra-interactive.py ; le spinner cyan est
remplace par un boot log revele ligne a ligne (~150ms) avec verification
reelle : OS (detect_current), Python (sys.version), reseau (socket github).
"""
from __future__ import annotations

import socket
import sys
import time
from dataclasses import dataclass

from rich.console import Console

from installer.core.osdetect import Distro, detect_current

from .theme import CRIT, OK, TITLE, WARN

_ASCII_LINES: tuple[tuple[str, float], ...] = (
    ("", 0.05),
    ("      ██╗  ██╗   ██╗██████╗  █████╗", 0.08),
    ("      ██║  ╚██╗ ██╔╝██╔══██╗██╔══██╗", 0.06),
    ("      ██║   ╚████╔╝ ██████╔╝███████║", 0.06),
    ("      ██║    ╚██╔╝  ██╔══██╗██╔══██║", 0.06),
    ("      ███████╗██║   ██║  ██║██║  ██║", 0.06),
    ("      ╚══════╝╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝", 0.10),
    ("", 0.05),
    ("      Assistant DevOps Vocal — Installateur v1", 0.12),
    ("", 0.05),
)

_LABEL_WIDTH = 14
_REVEAL_DELAY = 0.15


@dataclass(frozen=True)
class BootLine:
    label: str
    value: str
    level: str      # ok | warn | crit


def _check_os(distro: Distro) -> BootLine:
    level = "ok" if distro.supported else "warn"
    return BootLine("os", distro.pretty_name, level)


def _check_python() -> BootLine:
    version = f"{sys.version_info.major}.{sys.version_info.minor}"
    level = "ok" if sys.version_info >= (3, 10) else "warn"
    return BootLine("python", version, level)


def _check_network(host: str = "github.com", port: int = 22,
                   timeout: float = 2.0) -> BootLine:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return BootLine("reseau", "github joignable", "ok")
    except OSError:
        return BootLine("reseau", "github injoignable", "warn")


def gather_boot_lines() -> tuple[BootLine, ...]:
    """Verifications de boot (os, python, reseau)."""
    return (_check_os(detect_current()), _check_python(), _check_network())


def _level_style(level: str) -> str:
    return {"ok": OK, "warn": WARN}.get(level, CRIT)


def format_boot_line(line: BootLine) -> str:
    """'os ............ Fedora Linux 43' (dots de remplissage)."""
    dots = "." * max(2, _LABEL_WIDTH - len(line.label) - 1)
    return f"{line.label} {dots} {line.value}"


def run_boot(console: Console) -> None:
    """Animation de boot : art LYRA puis boot log revele ligne a ligne."""
    console.clear()
    for text, delay in _ASCII_LINES:
        if text:
            console.print(text, style=TITLE)
        else:
            console.print()
        time.sleep(delay)

    for line in gather_boot_lines():
        style = _level_style(line.level)
        console.print(
            f"      [{style}]{format_boot_line(line)}[/] "
            f"[bold {style}]\\[{line.level}][/]"
        )
        time.sleep(_REVEAL_DELAY)

    console.print()
    time.sleep(0.3)
