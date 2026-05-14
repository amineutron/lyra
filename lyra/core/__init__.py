"""
Lyra Core - Pipeline et configuration.

Components:
- RAGConfig: Configuration du systeme RAG
- Pipeline: Orchestration globale du workflow
"""

from .config import RAGConfig

# Pipeline non importe ici pour eviter de charger sentence_transformers/torch au demarrage.
# Importer directement: from lyra.core.pipeline import Pipeline

__all__ = [
    "RAGConfig",
]
