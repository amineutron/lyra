"""Etape : clone du repo Lyra (saute si on tourne deja dans un clone)."""
from __future__ import annotations

import subprocess

from ..events import Output
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


def _ssh_github_ok() -> bool:
    try:
        out = subprocess.run(
            ["ssh", "-T", "-o", "StrictHostKeyChecking=accept-new",
             "-o", "ConnectTimeout=8", "git@github.com"],
            capture_output=True, text=True, timeout=20)
        # GitHub repond code 1 avec un message de bienvenue si la cle est bonne
        return "successfully authenticated" in (out.stderr + out.stdout)
    except Exception:
        return False


def run_step(ctx: StepContext) -> None:
    lyra_dir = ctx.state.lyra_dir
    if _is_lyra_clone(lyra_dir):
        ctx.emit(Output(f"Deja dans un clone Lyra : {lyra_dir} (clone saute)"))
        return

    repo_url = ctx.state.repo_url
    if repo_url.startswith("git@") and not _ssh_github_ok():
        # Repos prives : fallback https + PAT saisi a la volee, jamais ecrit
        ctx.emit(Output("Cle SSH GitHub absente ou refusee."))
        token = ctx.broker.input(
            "Personal Access Token GitHub (https, non stocke)", default="")
        if not token:
            raise RuntimeError("acces au repo prive impossible (ni SSH ni PAT)")
        repo_name = repo_url.split(":", 1)[1]
        repo_url = f"https://{token}@github.com/{repo_name}"

    if lyra_dir.exists() and any(lyra_dir.iterdir()):
        raise RuntimeError(f"{lyra_dir} existe et n'est pas un clone Lyra")

    run(["git", "clone", repo_url, str(lyra_dir)], ctx.emit, step_id=ctx.step_id)
