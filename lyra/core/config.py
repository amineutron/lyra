"""
Lyra RAG - Configuration centralisee.

Charge et valide la configuration RAG depuis config.yaml.
"""

import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Any


@dataclass
class ChromaDBConfig:
    """Configuration ChromaDB."""
    persist_directory: str = ".chromadb"
    collection_name: str = "lyra_mcp_specs"
    embedding_model: str = "all-MiniLM-L6-v2"


@dataclass
class RetrievalConfig:
    """Configuration retrieval."""
    semantic_top_k: int = 5
    keyword_top_k: int = 5
    fusion_top_k: int = 3
    rrf_k: int = 60


@dataclass
class RAGModuleConfig:
    """Configuration module RAG."""
    enabled: bool = True
    chromadb: ChromaDBConfig = field(default_factory=ChromaDBConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)


@dataclass
class ModelConfig:
    """Configuration d'un modele LLM."""
    name: str
    temperature: float = 0.3


@dataclass
class ModelsConfig:
    """Configuration des modeles."""
    ephaistos: ModelConfig = field(default_factory=lambda: ModelConfig(
        name="qwen2.5-coder:7b",
        temperature=0.1
    ))
    lyra: ModelConfig = field(default_factory=lambda: ModelConfig(
        name="llama3.2:3b",
        temperature=0.5
    ))


@dataclass
class SessionConfig:
    """Configuration session."""
    max_turns: int = 10


@dataclass
class TrackingConfig:
    """Configuration du client tracking HTTP."""
    api_url: str = "http://127.0.0.1:8765"
    server_script: str = str(Path.home() / "dev" / "MCP" / "tracking" / "server.py")
    venv_python: str = str(Path.home() / "dev" / "MCP" / "tracking" / ".venv" / "bin" / "python")


@dataclass
class NotionConfig:
    """Configuration Notion (optionnel)."""
    enabled: bool = False
    database_id: Optional[str] = None
    token: Optional[str] = None


# Import lazy pour éviter circular imports
def _import_rag_enhanced_config():
    """Import lazy de RAGEnhancedConfig."""
    try:
        from ..rag_enhanced.config import RAGEnhancedConfig
        return RAGEnhancedConfig
    except ImportError:
        # Fallback si rag_enhanced pas encore implémenté
        return None


@dataclass
class RAGConfig:
    """Configuration complete du systeme RAG.

    Usage:
        config = RAGConfig.from_yaml("config.yaml")
        # ou
        config = RAGConfig.from_dict(config_dict)
    """
    rag: RAGModuleConfig = field(default_factory=RAGModuleConfig)
    models: ModelsConfig = field(default_factory=ModelsConfig)
    session: SessionConfig = field(default_factory=SessionConfig)
    notion: NotionConfig = field(default_factory=NotionConfig)
    tracking: TrackingConfig = field(default_factory=TrackingConfig)
    rag_enhanced: Optional[Any] = None  # RAGEnhancedConfig si disponible

    # Configuration LLM/MCP existante (pour compatibilite)
    llm: dict = field(default_factory=dict)
    mcp: dict = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "RAGConfig":
        """Charge la configuration depuis un fichier YAML."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "RAGConfig":
        """Construit la configuration depuis un dictionnaire."""
        config = cls()

        # RAG config
        if "rag" in data:
            rag_data = data["rag"]
            config.rag.enabled = rag_data.get("enabled", True)

            if "chromadb" in rag_data:
                chroma = rag_data["chromadb"]
                config.rag.chromadb = ChromaDBConfig(
                    persist_directory=chroma.get("persist_directory", ".chromadb"),
                    collection_name=chroma.get("collection_name", "lyra_mcp_specs"),
                    embedding_model=chroma.get("embedding_model", "all-MiniLM-L6-v2")
                )

            if "retrieval" in rag_data:
                ret = rag_data["retrieval"]
                config.rag.retrieval = RetrievalConfig(
                    semantic_top_k=ret.get("semantic_top_k", 5),
                    keyword_top_k=ret.get("keyword_top_k", 5),
                    fusion_top_k=ret.get("fusion_top_k", 3),
                    rrf_k=ret.get("rrf_k", 60)
                )

        # Models config
        if "models" in data:
            models_data = data["models"]

            if "ephaistos" in models_data:
                eph = models_data["ephaistos"]
                config.models.ephaistos = ModelConfig(
                    name=eph.get("name", "qwen2.5-coder:7b"),
                    temperature=eph.get("temperature", 0.1)
                )

            if "lyra" in models_data:
                lyra = models_data["lyra"]
                config.models.lyra = ModelConfig(
                    name=lyra.get("name", "llama3.2:3b"),
                    temperature=lyra.get("temperature", 0.5)
                )

        # Session config
        if "session" in data:
            config.session = SessionConfig(
                max_turns=data["session"].get("max_turns", 10)
            )

        # Notion config
        if "notion" in data:
            notion = data["notion"]
            config.notion = NotionConfig(
                enabled=notion.get("enabled", False),
                database_id=notion.get("database_id"),
                token=notion.get("token")
            )

        # Tracking config
        if "tracking" in data:
            t = data["tracking"]
            config.tracking = TrackingConfig(
                api_url=t.get("api_url", "http://127.0.0.1:8765"),
                server_script=t.get("server_script", TrackingConfig().server_script),
                venv_python=t.get("venv_python", TrackingConfig().venv_python),
            )

        # RAG Enhanced config (optionnel)
        if "rag_enhanced" in data:
            RAGEnhancedConfigClass = _import_rag_enhanced_config()
            if RAGEnhancedConfigClass:
                config.rag_enhanced = RAGEnhancedConfigClass.from_dict(data["rag_enhanced"])

        # Configs existantes (pass-through)
        config.llm = data.get("llm", {})
        config.mcp = data.get("mcp", {})

        return config

    def get_ollama_base_url(self) -> str:
        """Retourne l'URL de base Ollama."""
        return self.llm.get("base_url", "http://localhost:11434")

    def get_ollama_timeout(self) -> int:
        """Retourne le timeout Ollama."""
        return self.llm.get("timeout", 120)
