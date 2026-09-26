"""Etapes : venv Python + dependances pip (variante CPU sans CUDA)."""
from __future__ import annotations

import shutil

from ..events import Output
from ..pipeline import StepContext
from ..pipplan import pip_install_commands
from ..runner import pip_detail, run


def _find_python() -> str:
    for name in ("python3.11", "python3.12", "python3"):
        if shutil.which(name):
            return name
    raise RuntimeError("aucun python3 trouve")


def run_venv(ctx: StepContext) -> None:
    python = _find_python()
    venv_dir = ctx.state.lyra_dir / ".venv"
    ctx.emit(Output(f"Interpreteur : {python}"))
    if not venv_dir.exists():
        run([python, "-m", "venv", str(venv_dir)], ctx.emit, step_id=ctx.step_id)
    pip = str(venv_dir / "bin" / "pip")
    run([pip, "install", "--upgrade", "pip", "wheel", "setuptools"],
        ctx.emit, step_id=ctx.step_id, detail_fn=pip_detail)


def run_pip(ctx: StepContext) -> None:
    pip = str(ctx.state.lyra_dir / ".venv" / "bin" / "pip")
    for cmd in pip_install_commands(pip):
        run(cmd, ctx.emit, step_id=ctx.step_id, detail_fn=pip_detail)

