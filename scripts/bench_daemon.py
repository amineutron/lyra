#!/usr/bin/env python3
"""Benchmark avant/apres du chantier demon.

Rejoue les scenarios du plan (mesures AVANT du 2026-08-07 en dur) contre
l'installation courante (demon actif) et imprime le comparatif.

Usage: .venv/bin/python scripts/bench_daemon.py
Prerequis: demon demarre (le premier scenario le relance sinon).
"""

from __future__ import annotations

import json
import os
import pty
import select
import socket
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_common import BENCHMARKS, ecrire_resultat  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
LYRA = str(Path.home() / ".local" / "bin" / "lyra")

# Mesures de reference : dans un fichier, pas dans le code, pour qu'on puisse
# les rejouer et les comparer sans relire le script.
BASELINE = BENCHMARKS / "baseline-daemon-2026-08-07.json"
BEFORE = json.loads(BASELINE.read_text())["mesures_s"]


def timed(cmd: list[str], timeout: int = 300) -> float:
    start = time.perf_counter()
    subprocess.run(cmd, capture_output=True, timeout=timeout, cwd=REPO)
    return time.perf_counter() - start


def bench_repl_pret() -> float:
    """Temps entre le lancement du REPL et l'affichage du prompt."""
    master, slave = pty.openpty()
    proc = subprocess.Popen([LYRA], stdin=slave, stdout=slave, stderr=slave,
                            cwd=REPO, close_fds=True)
    os.close(slave)
    buf = b""
    t0 = time.time()
    pret = False
    fin = t0 + 120
    while time.time() < fin:
        r, _, _ = select.select([master], [], [], 0.1)
        if r:
            try:
                buf += os.read(master, 8192)
            except OSError:
                break
        if b"Vous >>" in buf:
            pret = True
            break
    duree = time.time() - t0
    try:
        os.write(master, b"quit\n")
        time.sleep(0.5)
    except OSError:
        pass
    proc.kill()
    os.close(master)
    if not pret:
        raise RuntimeError("le prompt du REPL n'est jamais apparu en 120 s")
    return duree


def _messages(sock: socket.socket, timeout_s: float):
    """Lit les messages JSON-lines du demon.

    Lecture bufferisee a la main : socket.makefile casse apres un timeout.
    """
    buf = b""
    fin = time.time() + timeout_s
    while time.time() < fin:
        sock.settimeout(max(0.1, fin - time.time()))
        try:
            bloc = sock.recv(65536)
        except (TimeoutError, OSError):
            return
        if not bloc:
            return
        buf += bloc
        while b"\n" in buf:
            ligne, buf = buf.split(b"\n", 1)
            if ligne.strip():
                yield json.loads(ligne)


def bench_premiere_requete(texte: str = "quel est le statut du denon",
                           timeout_s: float = 120.0) -> float:
    """Chronometre une requete complete via le socket du demon.

    On passe par le protocole (request -> result) et non par l'affichage du
    REPL : le texte de confirmation est redige par le modele LYRA et change
    d'une execution a l'autre. Guetter une phrase dans un PTY mesurait donc
    surtout des expirations de delai, enregistrees comme si c'etaient des
    latences.
    """
    chemin = Path.home() / ".lyra" / "lyra.sock"
    if not chemin.exists():
        raise RuntimeError(f"demon arrete : {chemin} absent")

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(10)
    sock.connect(str(chemin))

    def envoyer(message: dict) -> None:
        sock.sendall((json.dumps(message) + "\n").encode())

    try:
        envoyer({"type": "hello", "session": "bench", "client": "oneshot"})
        t0 = time.perf_counter()
        envoyer({"type": "request", "text": texte,
                 "options": {"yes": True, "verbose": False, "interactive": False}})
        for message in _messages(sock, timeout_s):
            mtype = message.get("type")
            if mtype == "ask":            # confirmation malgre yes : on repond
                envoyer({"type": "answer", "value": "o"})
            elif mtype == "result":
                return time.perf_counter() - t0
            elif mtype == "busy":
                raise RuntimeError(f"demon occupe : {message.get('text', '')}")
    finally:
        sock.close()

    raise RuntimeError(f"aucun 'result' recu en {timeout_s:.0f} s "
                       "(le banc refuse de publier une expiration comme latence)")


def main() -> None:
    print("Benchmark demon (les scenarios AVANT datent du 2026-08-07)\n")

    after_fast = timed([LYRA, "-y", "liste mes VMs"])
    after_full = timed([LYRA, "-y", "quels sont tes outils disponibles"])
    repl_ready = bench_repl_pret()
    repl_request = bench_premiere_requete()

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

    chemin = ecrire_resultat("daemon", {
        "baseline": BASELINE.name,
        "mesures_s": {
            "oneshot_fast": round(after_fast, 3),
            "oneshot_full": round(after_full, 3),
            "repl_ready": round(repl_ready, 3),
            "repl_first_request": round(repl_request, 3),
        },
    })
    print(f"\nResultat ecrit dans {chemin.relative_to(REPO)}")


if __name__ == "__main__":
    main()
