#!/usr/bin/env python3
"""Benchmark avant/apres du chantier demon.

Rejoue les scenarios du plan (mesures AVANT du 2026-08-07 en dur) contre
l'installation courante (demon actif) et imprime le comparatif.

Usage: .venv/bin/python scripts/bench_daemon.py
Prerequis: demon demarre (le premier scenario le relance sinon).
"""

from __future__ import annotations

import os
import pty
import select
import subprocess
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LYRA = str(Path.home() / ".local" / "bin" / "lyra")

BEFORE = {
    "oneshot_fast": 4.49,
    "oneshot_full": 17.08,
    "repl_ready": 20.0,     # 15-25s mesures, mediane
    "repl_first_request": 13.3,
}


def timed(cmd: list[str], timeout: int = 300) -> float:
    start = time.perf_counter()
    subprocess.run(cmd, capture_output=True, timeout=timeout, cwd=REPO)
    return time.perf_counter() - start


def bench_repl() -> tuple[float, float]:
    """(temps jusqu'au prompt, temps requete denon confirmee)."""
    master, slave = pty.openpty()
    proc = subprocess.Popen([LYRA], stdin=slave, stdout=slave, stderr=slave,
                            cwd=REPO, close_fds=True)
    os.close(slave)
    buf = b""

    def wait_for(marker: bytes, timeout: float) -> bool:
        nonlocal buf
        end = time.time() + timeout
        while time.time() < end:
            r, _, _ = select.select([master], [], [], 0.1)
            if r:
                try:
                    buf += os.read(master, 8192)
                except OSError:
                    return False
            if marker in buf:
                return True
        return False

    t0 = time.time()
    ready = wait_for(b"Vous >>", 120)
    t_ready = time.time() - t0

    t1 = time.time()
    os.write(master, b"quel est le statut du denon\n")
    if wait_for(b"C'est bon ?", 60):
        os.write(master, b"O\n")
    wait_for(b"volume", 60)
    t_request = time.time() - t1

    os.write(master, b"quit\n")
    time.sleep(1)
    proc.kill()
    if not ready:
        raise RuntimeError("prompt REPL jamais affiche")
    return t_ready, t_request


def main() -> None:
    print("Benchmark demon (les scenarios AVANT datent du 2026-08-07)\n")

    after_fast = timed([LYRA, "-y", "liste mes VMs"])
    after_full = timed([LYRA, "-y", "quels sont tes outils disponibles"])
    repl_ready, repl_request = bench_repl()

    rows = [
        ("One-shot fast-path (liste VMs)", BEFORE["oneshot_fast"], after_fast),
        ("One-shot pipeline complet", BEFORE["oneshot_full"], after_full),
        ("REPL: lancement -> pret", BEFORE["repl_ready"], repl_ready),
        ("REPL: premiere requete", BEFORE["repl_first_request"], repl_request),
    ]
    header = f"{'Scenario':<34} {'AVANT':>8} {'APRES':>8} {'gain':>7}"
    print(header)
    print("-" * len(header))
    for label, before, after in rows:
        gain = before / after if after > 0 else float("inf")
        print(f"{label:<34} {before:>7.2f}s {after:>7.2f}s {gain:>6.1f}x")


if __name__ == "__main__":
    main()
