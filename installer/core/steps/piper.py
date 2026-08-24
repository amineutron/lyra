"""Etapes : Piper TTS + voix francaise.

Les voix vont dans {lyra}/models/ : c'est la que /setting scanne les
*.onnx.json pour proposer les voix (cf. CLAUDE.md, Reglages utilisateur).
"""
from __future__ import annotations

from pathlib import Path

from ..events import Output
from ..pipeline import StepContext
from ..runner import run

_PIPER_URL = ("https://github.com/rhasspy/piper/releases/download/"
              "2023.11.14-2/piper_linux_x86_64.tar.gz")
_VOICE_BASE = ("https://huggingface.co/rhasspy/piper-voices/resolve/main/"
               "fr/fr_FR/upmc/medium/fr_FR-upmc-medium")


def run_piper(ctx: StepContext) -> None:
    piper_dir = Path.home() / ".local" / "piper"
    piper_bin = piper_dir / "piper" / "piper"
    if piper_bin.exists():
        ctx.emit(Output("Piper deja installe"))
    else:
        piper_dir.mkdir(parents=True, exist_ok=True)
        archive = piper_dir / "piper.tar.gz"
        run(["curl", "-fsSL", "-o", str(archive), _PIPER_URL],
            ctx.emit, step_id=ctx.step_id)
        run(["tar", "xzf", str(archive), "-C", str(piper_dir)],
            ctx.emit, step_id=ctx.step_id)
        archive.unlink(missing_ok=True)

    # Lien global : verifie meme si le binaire existait deja. -sfn remplace
    # un lien existant AU LIEU de descendre dedans (une vieille install
    # laissait /usr/local/bin/piper pointer sur le DOSSIER ~/.local/piper/
    # piper -> "same file" avec -sf).
    import os
    target = Path("/usr/local/bin/piper")
    link_ok = (target.is_file() and os.access(target, os.X_OK)
               and target.resolve() == piper_bin.resolve())
    if link_ok:
        ctx.emit(Output("Lien /usr/local/bin/piper deja correct"))
        return
    if ctx.broker.confirm("Creer le lien /usr/local/bin/piper (sudo) ?", True):
        run(["sudo", "ln", "-sfn", str(piper_bin), "/usr/local/bin/piper"],
            ctx.emit, step_id=ctx.step_id)


def run_voice(ctx: StepContext) -> None:
    models_dir = ctx.state.lyra_dir / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    for suffix in (".onnx", ".onnx.json"):
        target = models_dir / f"fr_FR-upmc-medium{suffix}"
        if target.exists():
            ctx.emit(Output(f"{target.name} deja present"))
            continue
        run(["curl", "-fsSL", "-o", str(target), _VOICE_BASE + suffix],
            ctx.emit, step_id=ctx.step_id)
