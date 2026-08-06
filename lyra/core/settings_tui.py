"""
Lyra Core - TUI interactif pour /setting.

Navigation aux fleches + Entree, retour avec Echap (ou q, ou Ctrl+C).
Utilise le mode cbreak du terminal ; la logique metier (persistance,
hot-swap, apercu vocal) reste dans SettingsMenu (settings_menu.py).

Fallback : si stdin n'est pas un TTY, main_rag.py utilise la machine a
etats texte de SettingsMenu a la place.
"""

from __future__ import annotations

import os
import select
import sys
import termios
import tty
from contextlib import contextmanager
from typing import Callable, Optional, TextIO

from .settings_menu import SPEED_PRESETS, SettingsMenu, parse_speed

_HIGHLIGHT = "\033[44;97m"  # fond bleu, texte blanc
_DIM = "\033[2m"
_RESET = "\033[0m"

_HINT = "fleches: naviguer   Entree: choisir   Echap: retour"


@contextmanager
def _cbreak(fd: int):
    """Mode cbreak temporaire (touche par touche, signaux actifs)."""
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _read_key(fd: int) -> str:
    """Lit une touche et la normalise: up/down/enter/esc ou le caractere.

    Lecture via os.read sur le fd (PAS sys.stdin.read : le TextIO bufferise
    les 3 octets d'une fleche et le select() suivant ne verrait plus rien,
    ce qui transformerait toute fleche en Echap).
    """
    ch = os.read(fd, 1).decode(errors="replace")
    if ch == "\x1b":
        # Distinguer Echap seul d'une sequence fleche (octets qui suivent)
        seq = b""
        while len(seq) < 2 and select.select([fd], [], [], 0.05)[0]:
            seq += os.read(fd, 2 - len(seq))
        return {b"[A": "up", b"[B": "down", b"[C": "right", b"[D": "left"}.get(seq, "esc")
    if ch in ("\r", "\n"):
        return "enter"
    return ch.lower()


def select_menu(
    title: str,
    items: list[str],
    index: int = 0,
    hint: str = _HINT,
    get_key: Optional[Callable[[], str]] = None,
    out: Optional[TextIO] = None,
) -> Optional[int]:
    """Menu de selection en place : retourne l'index choisi, None si annule.

    Args:
        title: Titre affiche au-dessus des items
        items: Lignes selectionnables
        index: Ligne pre-selectionnee
        hint: Ligne d'aide affichee en bas
        get_key: Source de touches (injectable pour les tests) ;
                 par defaut lecture cbreak du vrai terminal
        out: Sortie (injectable pour les tests) ; par defaut sys.stdout
    """
    if not items:
        return None
    out = out or sys.stdout
    index = max(0, min(index, len(items) - 1))
    n_lines = len(items) + 2  # titre + items + hint

    def draw(first: bool):
        if not first:
            out.write(f"\033[{n_lines}A")  # remonter pour redessiner en place
        out.write(f"\033[2K  {title}\n")
        for i, item in enumerate(items):
            if i == index:
                out.write(f"\033[2K  {_HIGHLIGHT} > {item} {_RESET}\n")
            else:
                out.write(f"\033[2K     {item}\n")
        out.write(f"\033[2K  {_DIM}{hint}{_RESET}\n")
        out.flush()

    def clear():
        out.write(f"\033[{n_lines}A\033[J")
        out.flush()

    def loop(read_key: Callable[[], str]) -> Optional[int]:
        nonlocal index
        draw(first=True)
        while True:
            try:
                key = read_key()
            except KeyboardInterrupt:
                clear()
                return None
            if key == "up":
                index = (index - 1) % len(items)
            elif key == "down":
                index = (index + 1) % len(items)
            elif key == "enter":
                clear()
                return index
            elif key in ("esc", "q"):
                clear()
                return None
            else:
                continue
            draw(first=False)

    if get_key is not None:
        return loop(get_key)

    fd = sys.stdin.fileno()
    out.write("\033[?25l")  # cacher le curseur
    try:
        with _cbreak(fd):
            return loop(lambda: _read_key(fd))
    finally:
        out.write("\033[?25h")
        out.flush()


def run_settings_tui(menu: SettingsMenu, println: Callable[[str], None] = print) -> None:
    """Boucle TUI complete : racine -> sous-menus -> application des choix.

    Args:
        menu: SettingsMenu (logique metier + callbacks hot-swap)
        println: Affichage des confirmations (injectable pour les tests)
    """
    while True:
        root_items = [
            f"Voix    : {menu.current_voice_label()}",
            f"Vitesse : {menu.current_speed_label()}",
            f"Mode    : {menu.callbacks.get_mode()}",
        ]
        choice = select_menu("Reglages Lyra", root_items,
                             hint=f"{_HINT}   Echap ici: fermer")
        if choice is None:
            println("Reglages fermes.")
            return
        if choice == 0:
            _voice_screen(menu, println)
        elif choice == 1:
            _speed_screen(menu, println)
        elif choice == 2:
            _mode_screen(menu, println)


def _voice_screen(menu: SettingsMenu, println: Callable[[str], None]) -> None:
    voices = menu.load_voices()
    current_model = menu.settings.get("tts.model", "fr_FR-upmc-medium")
    current_speaker = int(menu.settings.get("tts.speaker_id", 0))
    items, index = [], 0
    for i, voice in enumerate(voices):
        current = voice.model == current_model and voice.speaker_id == current_speaker
        items.append(f"{voice.label}{'  [actuelle]' if current else ''}")
        if current:
            index = i
    choice = select_menu("Voix disponibles", items, index=index)
    if choice is not None:
        println(menu.apply_voice_choice(voices[choice]))


def _speed_screen(menu: SettingsMenu, println: Callable[[str], None]) -> None:
    current = float(menu.settings.get("tts.length_scale", 1.0))
    items = [f"{preset} ({name})" for preset, name in SPEED_PRESETS]
    items.append("Valeur libre...")
    index = next((i for i, (preset, _) in enumerate(SPEED_PRESETS)
                  if abs(float(preset) - current) < 1e-9), 0)
    choice = select_menu("Vitesse de parole", items, index=index)
    if choice is None:
        return
    if choice < len(SPEED_PRESETS):
        println(menu.apply_speed_choice(float(SPEED_PRESETS[choice][0])))
        return
    # Saisie libre en mode terminal normal (hors cbreak)
    try:
        raw = input("  Vitesse (0.5 a 2.0) : ")
    except (KeyboardInterrupt, EOFError):
        return
    value = parse_speed(raw.strip())
    if value is None:
        println("Valeur invalide (attendu: nombre entre 0.5 et 2.0).")
        return
    println(menu.apply_speed_choice(value))


def _mode_screen(menu: SettingsMenu, println: Callable[[str], None]) -> None:
    current = menu.callbacks.get_mode()
    modes = ["default", "performance"]
    labels = {
        "default": "default (confirmation avant chaque action)",
        "performance": "performance (domotique sans confirmation)",
    }
    items = [f"{labels[m]}{'  [actuel]' if m == current else ''}" for m in modes]
    choice = select_menu("Mode", items, index=modes.index(current))
    if choice is not None:
        println(menu.apply_mode_choice(modes[choice]))
