"""Etape : clone du repo Lyra (saute si on tourne deja dans un clone)."""
from __future__ import annotations

import subprocess

from ..events import Output
from ..gitauth import resolve_repo_url
from ..pipeline import StepContext
from ..runner import run


def _is_lyra_clone(path) -> bool:
    try:
        out = subprocess.run(
            ["git", "-C", str(path), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=10)
        return out.returncode == 0 and "lyra" in out.stdout
    except Exception:
        return False


def run_step(ctx: StepContext) -> None:
    lyra_dir = ctx.state.lyra_dir
    if _is_lyra_clone(lyra_dir):
        ctx.emit(Output(f"Deja dans un clone Lyra : {lyra_dir} (clone saute)"))
        return

    repo_url = resolve_repo_url(ctx, ctx.state.repo_url)

    if lyra_dir.exists() and any(lyra_dir.iterdir()):
        raise RuntimeError(f"{lyra_dir} existe et n'est pas un clone Lyra")

    run(["git", "clone", repo_url, str(lyra_dir)], ctx.emit, step_id=ctx.step_id)
