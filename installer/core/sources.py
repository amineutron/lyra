"""Ce que l'installeur telecharge (modeles, Piper, voix). SANS dependance.

steps/ollama.py et steps/piper.py tirent pipeline -> catalog -> yaml ;
installer/bundle.py (installation hors ligne, Python nu du systeme) importait
ces constantes par la et echouait sans pyyaml. Elles vivent donc ici.
"""
from __future__ import annotations

import os

MODELS = ["qwen2.5-coder:0.5b", "llama3.2:1b"]

PIPER_URL = ("https://github.com/rhasspy/piper/releases/download/"
             "2023.11.14-2/piper_linux_x86_64.tar.gz")
# HF_ENDPOINT : miroir Hugging Face d'entreprise (meme variable que huggingface_hub)
VOICE_BASE = (os.environ.get("HF_ENDPOINT", "https://huggingface.co").rstrip("/")
              + "/rhasspy/piper-voices/resolve/main/fr/fr_FR/upmc/medium/fr_FR-upmc-medium")
