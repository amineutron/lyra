"""
Lyra Models - Dual model architecture.

Components:
- Ephaistos: Backend Qwen 7B pour analyse specs MCP
- LyraVoice: Frontend Llama 3B pour dialogue friendly
- ModelManager: Orchestration des deux modeles
"""

__all__ = [
    "Ephaistos",
    "LyraVoice",
    "ModelManager",
]


def __getattr__(name: str):
    """Imports lazys pour eviter les imports circulaires."""
    if name == "Ephaistos":
        from .ephaistos import Ephaistos
        return Ephaistos
    if name == "LyraVoice":
        from .lyra_voice import LyraVoice
        return LyraVoice
    if name == "ModelManager":
        from .model_manager import ModelManager
        return ModelManager
    raise AttributeError(f"module 'lyra.models' has no attribute {name!r}")
