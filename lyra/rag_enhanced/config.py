"""
Configuration RAG Enhanced.

Charge et valide la configuration du système RAG Enhanced depuis config.yaml.
"""

from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

from .constants import (
    SLANG_MAX_PATTERNS,
    SYNONYM_MAX_PER_KEYWORD,
    SYNONYM_MAX_TOKENS_ADDED,
    CONTEXT_DEFAULT_WINDOW,
    CONTEXT_MAX_WINDOW,
    CONTEXT_FIFO_LIMIT,
    CONTEXT_CACHE_TTL,
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    FEEDBACK_SUGGESTION_THRESHOLD,
    FEEDBACK_AUTO_THRESHOLD,
    RAG_3TIER_COLLECTIONS,
)


@dataclass
class SlangNormalizerConfig:
    """Configuration du Slang Normalizer.

    Attributes:
        enabled: Activer le normalizer
        dict_path: Chemin vers slang_dict.json
        max_patterns: Max patterns dans le dictionnaire
        log_normalizations: Logger les normalisations
    """
    enabled: bool = False
    dict_path: str = "data/slang_dict.json"
    max_patterns: int = SLANG_MAX_PATTERNS
    log_normalizations: bool = True

    def __post_init__(self):
        """Validation des valeurs."""
        if self.max_patterns < 0:
            raise ValueError(f"max_patterns doit être >= 0, got {self.max_patterns}")
        if self.max_patterns > SLANG_MAX_PATTERNS:
            raise ValueError(
                f"max_patterns ne peut pas dépasser {SLANG_MAX_PATTERNS}, got {self.max_patterns}"
            )


@dataclass
class SynonymExpanderConfig:
    """Configuration du Synonym Expander.

    Attributes:
        enabled: Activer l'expander
        dict_path: Chemin vers synonym_dict.json
        max_synonyms: Max synonymes par mot-clé
        max_tokens_added: Max tokens ajoutés à la requête
    """
    enabled: bool = False
    dict_path: str = "data/synonym_dict.json"
    max_synonyms: int = SYNONYM_MAX_PER_KEYWORD
    max_tokens_added: int = SYNONYM_MAX_TOKENS_ADDED

    def __post_init__(self):
        """Validation des valeurs."""
        if self.max_synonyms < 0:
            raise ValueError(f"max_synonyms doit être >= 0, got {self.max_synonyms}")
        if self.max_tokens_added < 0:
            raise ValueError(f"max_tokens_added doit être >= 0, got {self.max_tokens_added}")


@dataclass
class ContextInjectorConfig:
    """Configuration du Context Injector.

    Attributes:
        enabled: Activer l'injector
        db_path: Chemin vers session_history.db
        default_window: N échanges par défaut
        max_window: Max échanges injectables
        fifo_limit: Max échanges conservés par session
    """
    enabled: bool = False
    db_path: str = "data/session_history.db"
    default_window: int = CONTEXT_DEFAULT_WINDOW
    max_window: int = CONTEXT_MAX_WINDOW
    fifo_limit: int = CONTEXT_FIFO_LIMIT
    cache_ttl: int = CONTEXT_CACHE_TTL

    def __post_init__(self):
        """Validation des valeurs."""
        if self.default_window < 0 or self.default_window > self.max_window:
            raise ValueError(
                f"default_window doit être entre 0 et {self.max_window}, got {self.default_window}"
            )
        if self.fifo_limit < self.max_window:
            raise ValueError(
                f"fifo_limit doit être >= max_window ({self.max_window}), got {self.fifo_limit}"
            )


@dataclass
class RAG3TierConfig:
    """Configuration RAG 3-Tier.

    Attributes:
        enabled: Activer RAG 3-Tier
        collections: Liste des 3 collections ChromaDB
        cascade_strategy: Stratégie cascade ("early_stop" ou "full_scan")
    """
    enabled: bool = False
    collections: list[str] = field(default_factory=lambda: RAG_3TIER_COLLECTIONS.copy())
    cascade_strategy: str = "early_stop"

    def __post_init__(self):
        """Validation des valeurs."""
        if len(self.collections) != 3:
            raise ValueError(f"RAG 3-Tier nécessite exactement 3 collections, got {len(self.collections)}")
        if self.cascade_strategy not in ["early_stop", "full_scan"]:
            raise ValueError(
                f"cascade_strategy doit être 'early_stop' ou 'full_scan', got {self.cascade_strategy}"
            )


@dataclass
class FeedbackLoopConfig:
    """Configuration Feedback Loop.

    Attributes:
        enabled: Activer le feedback loop
        confidence_high: Seuil haute confiance
        confidence_low: Seuil basse confiance
        suggestion_threshold: Échecs avant suggestion
        auto_threshold: Échecs avant auto-enrichissement
    """
    enabled: bool = False
    confidence_high: float = CONFIDENCE_HIGH
    confidence_low: float = CONFIDENCE_LOW
    suggestion_threshold: int = FEEDBACK_SUGGESTION_THRESHOLD
    auto_threshold: int = FEEDBACK_AUTO_THRESHOLD

    def __post_init__(self):
        """Validation des valeurs."""
        if not (0.0 <= self.confidence_low <= self.confidence_high <= 1.0):
            raise ValueError(
                f"Seuils invalides: confidence_low={self.confidence_low}, "
                f"confidence_high={self.confidence_high}"
            )
        if self.suggestion_threshold >= self.auto_threshold:
            raise ValueError(
                f"suggestion_threshold ({self.suggestion_threshold}) doit être "
                f"< auto_threshold ({self.auto_threshold})"
            )


@dataclass
class MetricsConfig:
    """Configuration métriques.

    Attributes:
        enabled: Activer le tracking métriques
        log_path: Chemin vers fichier JSONL de métriques
    """
    enabled: bool = True
    log_path: str = "logs/rag_enhanced_metrics.jsonl"


@dataclass
class RAGEnhancedConfig:
    """Configuration complète RAG Enhanced.

    Usage:
        config = RAGEnhancedConfig.from_dict(yaml_data)
        if config.enabled and config.slang_normalizer.enabled:
            normalizer = SlangNormalizer(config.slang_normalizer)
    """
    enabled: bool = False
    slang_normalizer: SlangNormalizerConfig = field(default_factory=SlangNormalizerConfig)
    synonym_expander: SynonymExpanderConfig = field(default_factory=SynonymExpanderConfig)
    context_injector: ContextInjectorConfig = field(default_factory=ContextInjectorConfig)
    rag_3tier: RAG3TierConfig = field(default_factory=RAG3TierConfig)
    feedback_loop: FeedbackLoopConfig = field(default_factory=FeedbackLoopConfig)
    metrics: MetricsConfig = field(default_factory=MetricsConfig)

    @classmethod
    def from_dict(cls, data: dict) -> "RAGEnhancedConfig":
        """Construit la configuration depuis un dictionnaire.

        Args:
            data: Dictionnaire de configuration (section 'rag_enhanced' de config.yaml)

        Returns:
            Instance de RAGEnhancedConfig

        Raises:
            ValueError: Si validation échoue
        """
        config = cls()
        config.enabled = data.get("enabled", False)

        # Slang Normalizer
        if "slang_normalizer" in data:
            slang_data = data["slang_normalizer"]
            config.slang_normalizer = SlangNormalizerConfig(
                enabled=slang_data.get("enabled", False),
                dict_path=slang_data.get("dict_path", "data/slang_dict.json"),
                max_patterns=slang_data.get("max_patterns", SLANG_MAX_PATTERNS),
                log_normalizations=slang_data.get("log_normalizations", True),
            )

        # Synonym Expander
        if "synonym_expander" in data:
            syn_data = data["synonym_expander"]
            config.synonym_expander = SynonymExpanderConfig(
                enabled=syn_data.get("enabled", False),
                dict_path=syn_data.get("dict_path", "data/synonym_dict.json"),
                max_synonyms=syn_data.get("max_synonyms", SYNONYM_MAX_PER_KEYWORD),
                max_tokens_added=syn_data.get("max_tokens_added", SYNONYM_MAX_TOKENS_ADDED),
            )

        # Context Injector
        if "context_injector" in data:
            ctx_data = data["context_injector"]
            config.context_injector = ContextInjectorConfig(
                enabled=ctx_data.get("enabled", False),
                db_path=ctx_data.get("db_path", "data/session_history.db"),
                default_window=ctx_data.get("default_window", CONTEXT_DEFAULT_WINDOW),
                max_window=ctx_data.get("max_window", CONTEXT_MAX_WINDOW),
                fifo_limit=ctx_data.get("fifo_limit", CONTEXT_FIFO_LIMIT),
                cache_ttl=ctx_data.get("cache_ttl", CONTEXT_CACHE_TTL),
            )

        # RAG 3-Tier
        if "rag_3tier" in data:
            rag_data = data["rag_3tier"]
            config.rag_3tier = RAG3TierConfig(
                enabled=rag_data.get("enabled", False),
                collections=rag_data.get("collections", RAG_3TIER_COLLECTIONS.copy()),
                cascade_strategy=rag_data.get("cascade_strategy", "early_stop"),
            )

        # Feedback Loop
        if "feedback_loop" in data:
            fb_data = data["feedback_loop"]
            config.feedback_loop = FeedbackLoopConfig(
                enabled=fb_data.get("enabled", False),
                confidence_high=fb_data.get("confidence_high", CONFIDENCE_HIGH),
                confidence_low=fb_data.get("confidence_low", CONFIDENCE_LOW),
                suggestion_threshold=fb_data.get("suggestion_threshold", FEEDBACK_SUGGESTION_THRESHOLD),
                auto_threshold=fb_data.get("auto_threshold", FEEDBACK_AUTO_THRESHOLD),
            )

        # Metrics
        if "metrics" in data:
            metrics_data = data["metrics"]
            config.metrics = MetricsConfig(
                enabled=metrics_data.get("enabled", True),
                log_path=metrics_data.get("log_path", "logs/rag_enhanced_metrics.jsonl"),
            )

        return config
