"""Executeur de commandes streamable.

Porte de _run_cmd (install-lyra-interactive.py) : Popen + streaming ligne a
ligne vers emit(Output). Jamais shell=True ici — le seul cas legitime
(curl | sh d'Ollama) est isole dans steps/ollama.py et documente.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Callable, Optional

from .events import Emit, Output, Progress


class CommandError(RuntimeError):
    def __init__(self, cmd: list[str], returncode: int, tail: list[str]):
        self.cmd = cmd
        self.returncode = returncode
        self.tail = tail
        pretty = " ".join(cmd)
        detail = " | ".join(tail[-3:]) if tail else ""
        super().__init__(f"commande '{pretty}' a echoue (code {returncode})"
                         + (f" : {detail}" if detail else ""))


def run(cmd: list[str], emit: Emit, *,
        step_id: str = "",
        cwd: Optional[Path] = None,
        env: Optional[dict] = None,
        check: bool = True,
        detail_fn: Optional[Callable[[str], Optional[str]]] = None) -> int:
    """Execute cmd, streame stdout+stderr ligne a ligne via emit."""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)

    proc = subprocess.Popen(
        cmd, cwd=str(cwd) if cwd else None, env=full_env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )
    tail: list[str] = []
    assert proc.stdout is not None
    for raw in proc.stdout:
        for line in raw.replace("\r", "\n").split("\n"):
            line = line.strip()
            if not line:
                continue
            emit(Output(line))
            tail.append(line)
            if len(tail) > 10:
                tail.pop(0)
            if detail_fn and step_id:
                detail = detail_fn(line)
                if detail:
                    emit(Progress(step_id=step_id, detail=detail))
    proc.wait()
    if check and proc.returncode != 0:
        raise CommandError(cmd, proc.returncode, tail)
    return proc.returncode


def pip_detail(line: str) -> Optional[str]:
    """Extrait le nom du paquet depuis la sortie pip (Collecting X)."""
    line = line.strip()
    if line.startswith("Collecting "):
        return line[11:].split()[0].split("<")[0].split(">")[0].split("=")[0][:30]
    if "Installing collected" in line:
        return "installation..."
    return None
