"""Etapes : venv Python + dependances pip (variante CPU sans CUDA)."""
from __future__ import annotations

import shutil

from ..events import Output
from ..pipeline import StepContext
from ..runner import pip_detail, run

# 3 blocs identiques a l'ancien installeur (variante CPU) :
# 1) noyau ; 2) sentence-transformers sans deps (evite PyTorch CUDA) ;
# 3) deps de sentence-transformers en CPU.
_PIP_CORE = [
    "chromadb", "rank-bm25", "faster-whisper>=0.10.0", "pyyaml", "requests",
    "ollama", "httpx", "pydantic", "pydantic-settings", "python-dotenv",
    "rich", "sounddevice", "numpy", "pexpect", "pathvalidate",
]
_PIP_ST_DEPS = [
    "transformers", "huggingface-hub", "tokenizers", "scikit-learn",
    "scipy", "tqdm", "pillow", "filelock", "fsspec", "safetensors",
]


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
    run([pip, "install"] + _PIP_CORE, ctx.emit,
        step_id=ctx.step_id, detail_fn=pip_detail)
    # torch CPU (~200 Mo au lieu de ~2.5 Go CUDA) : requis au runtime par
    # sentence-transformers — sans lui le RAG plante au chargement.
    run([pip, "install", "torch", "--index-url",
         "https://download.pytorch.org/whl/cpu"], ctx.emit,
        step_id=ctx.step_id, detail_fn=pip_detail)
    run([pip, "install", "--no-deps", "sentence-transformers"], ctx.emit,
        step_id=ctx.step_id, detail_fn=pip_detail)
    run([pip, "install"] + _PIP_ST_DEPS, ctx.emit,
        step_id=ctx.step_id, detail_fn=pip_detail)
