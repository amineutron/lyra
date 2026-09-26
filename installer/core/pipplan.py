"""Plan d'installation des dependances Python de Lyra (variante CPU sans CUDA).

Source unique, SANS dependance (pas de yaml, pas de pipeline) : l'installeur
(steps/venv.py) et l'image d'evaluation (deploy/eval/Containerfile, Python nu)
l'executent tous deux.
"""
from __future__ import annotations

import os
from typing import Mapping

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


TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"


def pip_install_commands(pip: str, environ: Mapping[str, str] | None = None) -> list[list[str]]:
    """Les commandes pip du venv Lyra, dans l'ordre. Source unique : l'installeur
    et l'image d'evaluation (deploy/eval/Containerfile) les executent toutes deux.

    torch CPU (~200 Mo au lieu de ~2.5 Go CUDA) : requis au runtime par
    sentence-transformers -- sans lui le RAG plante au chargement. Son index
    se change par LYRA_TORCH_INDEX_URL (miroir d'entreprise des wheels CPU)."""
    env = os.environ if environ is None else environ
    torch_index = env.get("LYRA_TORCH_INDEX_URL", "").strip() or TORCH_CPU_INDEX
    return [
        [pip, "install", *_PIP_CORE],
        [pip, "install", "torch", "--index-url", torch_index],
        [pip, "install", "--no-deps", "sentence-transformers"],
        [pip, "install", *_PIP_ST_DEPS],
    ]


if __name__ == "__main__":  # python -m installer.core.pipplan --pip <chemin/vers/pip>
    import argparse
    import subprocess

    parser = argparse.ArgumentParser(description="Installe les dependances Python de Lyra dans un venv")
    parser.add_argument("--pip", required=True)
    for command in pip_install_commands(parser.parse_args().pip):
        subprocess.run(command, check=True)
