"""
Lyra RAG Enhanced - Système RAG amélioré.

Enrichit le pipeline RAG V2 avec :
- Slang Normalizer : Normalisation anglicismes → français
- Synonym Expander : Expansion synonymes
- Context Injector : Injection contexte session (SQLite)
- RAG 3-Tier : 3 collections ChromaDB en entonnoir
- Feedback Loop : Apprentissage continu
- Confidence Cascader : Seuils de confiance (0.85/0.60)
"""

from .types import (
    ConfidenceLevel,
    CascadeAction,
    QueryContext,
    RAGResult,
    FeedbackEntry,
)

from .config import (
    RAGEnhancedConfig,
    SlangNormalizerConfig,
    SynonymExpanderConfig,
    ContextInjectorConfig,
    RAG3TierConfig,
    FeedbackLoopConfig,
    MetricsConfig,
)

from .constants import (
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_LOW,
    SLANG_MAX_PATTERNS,
    SYNONYM_MAX_PER_KEYWORD,
    SYNONYM_MAX_TOKENS_ADDED,
    CONTEXT_DEFAULT_WINDOW,
    CONTEXT_MAX_WINDOW,
    CONTEXT_FIFO_LIMIT,
)

# Composants (SESSION 2+)
try:
    from .slang_normalizer import SlangNormalizer, get_default_normalizer
except ImportError:
    # Pas encore implémenté
    SlangNormalizer = None
    get_default_normalizer = None

# SESSION 3
try:
    from .synonym_expander import SynonymExpander, get_synonym_expander
except ImportError:
    # Pas encore implémenté
    SynonymExpander = None
    get_synonym_expander = None

# SESSION 4
try:
    from .context_db import ContextDB, get_context_db
    from .context_injector import ContextInjector, get_context_injector
except ImportError:
    # Pas encore implémenté
    ContextDB = None
    get_context_db = None
    ContextInjector = None
    get_context_injector = None

# SESSION 5
try:
    from .rag_3tier import RAG3Tier, get_rag_3tier
except ImportError:
    # Pas encore implémenté
    RAG3Tier = None
    get_rag_3tier = None

# SESSION 6
try:
    from .feedback_loop import FeedbackLoop, get_feedback_loop
    from .confidence_cascader import ConfidenceCascader, get_confidence_cascader
except ImportError:
    # Pas encore implémenté
    FeedbackLoop = None
    get_feedback_loop = None
    ConfidenceCascader = None
    get_confidence_cascader = None

# SESSION 7
try:
    from .pipeline_enhanced import EnhancedPipeline, EnhancedPipelineResult
except ImportError:
    # Pas encore implémenté
    EnhancedPipeline = None
    EnhancedPipelineResult = None

__all__ = [
    # Types
    "ConfidenceLevel",
    "CascadeAction",
    "QueryContext",
    "RAGResult",
    "FeedbackEntry",
    # Config
    "RAGEnhancedConfig",
    "SlangNormalizerConfig",
    "SynonymExpanderConfig",
    "ContextInjectorConfig",
    "RAG3TierConfig",
    "FeedbackLoopConfig",
    "MetricsConfig",
    # Constants
    "CONFIDENCE_HIGH",
    "CONFIDENCE_MEDIUM",
    "CONFIDENCE_LOW",
    "SLANG_MAX_PATTERNS",
    "SYNONYM_MAX_PER_KEYWORD",
    "SYNONYM_MAX_TOKENS_ADDED",
    "CONTEXT_DEFAULT_WINDOW",
    "CONTEXT_MAX_WINDOW",
    "CONTEXT_FIFO_LIMIT",
    # Composants
    "SlangNormalizer",
    "get_default_normalizer",
    "SynonymExpander",
    "get_synonym_expander",
    "ContextDB",
    "get_context_db",
    "ContextInjector",
    "get_context_injector",
    "RAG3Tier",
    "get_rag_3tier",
    "FeedbackLoop",
    "get_feedback_loop",
    "ConfidenceCascader",
    "get_confidence_cascader",
    # Pipeline Enhanced
    "EnhancedPipeline",
    "EnhancedPipelineResult",
]

__version__ = "0.1.0"
