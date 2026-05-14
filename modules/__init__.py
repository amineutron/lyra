"""
Lyra V1 - Modules Package

Contains the core modules for the voice assistant:
- llm: LLM client (Ollama)
- mcp: MCP tool invocation
- ui: User interface (confirmation, display)
- audio: STT/TTS (faster-whisper + Piper)
"""

from . import llm
from . import mcp
from . import ui

# Audio est importe a la demande pour eviter de charger les modeles inutilement
# from . import audio

__all__ = ["llm", "mcp", "ui", "audio"]
