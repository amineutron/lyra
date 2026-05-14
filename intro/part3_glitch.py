#!/usr/bin/env python3
"""
Lyra Intro - Transition glitch entre le boot screen et la video d'activation.
"""
import sys
import time
import random
import os

GLITCH_CHARS = "!@#$%^&*<>?/|\\[]{}~`01"
COLS = os.get_terminal_size().columns
ROWS = os.get_terminal_size().lines

CYAN  = "\033[96m"
WHITE = "\033[97m"
DIM   = "\033[2;36m"
RED   = "\033[91m"
RESET = "\033[0m"
CLEAR = "\033[2J\033[H"
HIDE  = "\033[?25l"
SHOW  = "\033[?25h"


def rand_line(width: int, density: float = 0.6) -> str:
    colors = [CYAN, WHITE, DIM, RED, CYAN, CYAN]
    parts = []
    i = 0
    while i < width:
        if random.random() < density:
            c = random.choice(colors)
            ch = random.choice(GLITCH_CHARS)
            parts.append(f"{c}{ch}{RESET}")
            i += 1
        else:
            skip = random.randint(1, 4)
            parts.append(" " * skip)
            i += skip
    return "".join(parts)


def glitch_frame(intensity: float) -> None:
    sys.stdout.write("\033[H")  # revient en haut sans effacer
    for row in range(ROWS):
        if random.random() < intensity:
            line = rand_line(COLS, density=intensity)
        else:
            line = " " * COLS
        sys.stdout.write(line + "\n")
    sys.stdout.flush()


def run() -> None:
    sys.stdout.write(HIDE)
    sys.stdout.write(CLEAR)
    sys.stdout.flush()

    # Phase 1 : glitch monte en intensite (0.3s)
    steps = [0.15, 0.25, 0.4, 0.6, 0.8, 1.0, 0.9, 1.0]
    for intensity in steps:
        glitch_frame(intensity)
        time.sleep(0.04)

    # Phase 2 : flash blanc total
    sys.stdout.write("\033[H")
    for _ in range(ROWS):
        sys.stdout.write(f"{WHITE}" + ("█" * COLS) + f"{RESET}\n")
    sys.stdout.flush()
    time.sleep(0.06)

    # Phase 3 : glitch rapide post-flash
    for intensity in [0.7, 0.5, 0.3, 0.15, 0.05]:
        glitch_frame(intensity)
        time.sleep(0.04)

    # Ecran noir propre pour la video
    sys.stdout.write(CLEAR)
    sys.stdout.flush()
    sys.stdout.write(SHOW)


if __name__ == "__main__":
    run()
