"""
Lyra RAG - Architecture hybride avec dual models et RAG.

Modules:
- rag: Systeme de retrieval hybride (ChromaDB + BM25 + RRF)
- models: Dual models EPHAISTOS (Qwen 7B) + LYRA (Llama 3B)
- hestia: Executeur MCP avec logging optionnel
- core: Pipeline et configuration
"""

__version__ = "2.0.0"
