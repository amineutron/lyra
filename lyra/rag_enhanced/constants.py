"""
Constantes pour le système RAG Enhanced.

Limites et seuils basés sur le TOPO de spécification.
"""

# =============================================================================
# Seuils de confiance
# =============================================================================
CONFIDENCE_HIGH = 0.80    # Seuil haute confiance (confirmation courte)
CONFIDENCE_MEDIUM = 0.50  # Seuil moyenne confiance (vérif état + confirmation serveur)
CONFIDENCE_LOW = 0.50     # En dessous = fallback LYRA (incertitude exprimée)

# =============================================================================
# Limites Slang Normalizer
# =============================================================================
SLANG_MAX_PATTERNS = 200  # Max patterns dans slang_dict.json

# =============================================================================
# Limites Synonym Expander
# =============================================================================
SYNONYM_MAX_PER_KEYWORD = 6   # Max synonymes par mot-clé
SYNONYM_MAX_TOKENS_ADDED = 15  # Max tokens ajoutés à la requête
SYNONYM_MAX_KEYWORDS = 80      # Max keywords dans synonym_dict.json

# =============================================================================
# Limites Context Injector
# =============================================================================
CONTEXT_DEFAULT_WINDOW = 5   # N échanges injectés par défaut
CONTEXT_MAX_WINDOW = 15      # Max échanges injectables
CONTEXT_FIFO_LIMIT = 15      # Max échanges conservés par session
CONTEXT_CACHE_TTL = 3600     # TTL cache SQLite (secondes)

# =============================================================================
# Seuils Feedback Loop
# =============================================================================
FEEDBACK_SUGGESTION_THRESHOLD = 3  # Échecs avant suggestion
FEEDBACK_AUTO_THRESHOLD = 5        # Échecs avant auto-enrichissement
FEEDBACK_PROMOTION_THRESHOLD = 50  # Hits avant promotion (temp → permanent)
FEEDBACK_WINDOW_SIZE = 10          # Fenêtre glissante pour stats

# =============================================================================
# RAG 3-Tier Collections
# =============================================================================
RAG_3TIER_COLLECTIONS = [
    "lyra_mcp_registry_v3",
    "lyra_mcp_capabilities_v3",
    "lyra_mcp_parameters_v3"
]

# =============================================================================
# Performance Limits
# =============================================================================
SLANG_NORMALIZER_MAX_LATENCY_MS = 1    # <1ms par requête
SYNONYM_EXPANDER_MAX_LATENCY_MS = 1    # <1ms par requête
CONTEXT_INJECTOR_MAX_LATENCY_MS = 10   # <10ms (SQLite query)
FEEDBACK_LOOP_MAX_LATENCY_MS = 2       # <2ms overhead
TOTAL_OVERHEAD_MAX_MS = 50             # <50ms total vs V2

# =============================================================================
# RAG 3-Tier Strategy
# =============================================================================
RAG_3TIER_EARLY_STOP_THRESHOLD = 0.80  # Stop cascade si score >0.80
RAG_3TIER_CONTEXT_GAP_THRESHOLD = 0.10  # Inject context si gap <0.10
