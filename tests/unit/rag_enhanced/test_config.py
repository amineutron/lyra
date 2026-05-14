"""
Tests unitaires pour la configuration RAG Enhanced.
"""

import pytest
import yaml
from pathlib import Path
from lyra.rag_enhanced.config import (
    RAGEnhancedConfig,
    SlangNormalizerConfig,
    SynonymExpanderConfig,
    ContextInjectorConfig,
    RAG3TierConfig,
    FeedbackLoopConfig,
    MetricsConfig,
)
from lyra.rag_enhanced.types import QueryContext, RAGResult, ConfidenceLevel, CascadeAction
from lyra.rag_enhanced.constants import SLANG_MAX_PATTERNS, CONFIDENCE_HIGH


def test_load_rag_enhanced_config(sample_config_dict):
    """Charge config depuis dict."""
    config = RAGEnhancedConfig.from_dict(sample_config_dict)

    assert config is not None
    assert hasattr(config, 'enabled')
    assert config.enabled is True
    assert config.slang_normalizer.enabled is True
    assert config.synonym_expander.enabled is True


def test_config_defaults():
    """Valeurs par défaut correctes."""
    config = RAGEnhancedConfig()

    # Master switch disabled par défaut
    assert config.enabled is False

    # Slang Normalizer
    assert config.slang_normalizer.enabled is False
    assert config.slang_normalizer.max_patterns == SLANG_MAX_PATTERNS
    assert config.slang_normalizer.dict_path == "data/slang_dict.json"

    # Synonym Expander
    assert config.synonym_expander.enabled is False
    assert config.synonym_expander.max_synonyms == 6
    assert config.synonym_expander.max_tokens_added == 15

    # Context Injector
    assert config.context_injector.enabled is False
    assert config.context_injector.default_window == 5
    assert config.context_injector.max_window == 15
    assert config.context_injector.fifo_limit == 15
    assert config.context_injector.cache_ttl == 3600

    # RAG 3-Tier
    assert config.rag_3tier.enabled is False
    assert len(config.rag_3tier.collections) == 3
    assert config.rag_3tier.cascade_strategy == "early_stop"

    # Feedback Loop
    assert config.feedback_loop.enabled is False
    assert config.feedback_loop.confidence_high == 0.80
    assert config.feedback_loop.confidence_low == 0.50
    assert config.feedback_loop.suggestion_threshold == 3
    assert config.feedback_loop.auto_threshold == 5

    # Metrics
    assert config.metrics.enabled is True
    assert config.metrics.log_path == "logs/rag_enhanced_metrics.jsonl"


def test_config_validation():
    """Validation des valeurs."""
    # Test 1: max_patterns négatif
    with pytest.raises(ValueError, match="max_patterns doit être >= 0"):
        SlangNormalizerConfig(max_patterns=-1)

    # Test 2: max_patterns > limite
    with pytest.raises(ValueError, match=f"max_patterns ne peut pas dépasser {SLANG_MAX_PATTERNS}"):
        SlangNormalizerConfig(max_patterns=300)

    # Test 3: max_synonyms négatif
    with pytest.raises(ValueError, match="max_synonyms doit être >= 0"):
        SynonymExpanderConfig(max_synonyms=-1)

    # Test 4: default_window > max_window
    with pytest.raises(ValueError, match="default_window doit être entre 0 et"):
        ContextInjectorConfig(default_window=20, max_window=15)

    # Test 5: fifo_limit < max_window
    with pytest.raises(ValueError, match="fifo_limit doit être >= max_window"):
        ContextInjectorConfig(max_window=15, fifo_limit=10)

    # Test 6: RAG 3-Tier pas exactement 3 collections
    with pytest.raises(ValueError, match="RAG 3-Tier nécessite exactement 3 collections"):
        RAG3TierConfig(collections=["col1", "col2"])

    # Test 7: cascade_strategy invalide
    with pytest.raises(ValueError, match="cascade_strategy doit être"):
        RAG3TierConfig(cascade_strategy="invalid")

    # Test 8: confidence_high > 1.0
    with pytest.raises(ValueError, match="Seuils invalides"):
        FeedbackLoopConfig(confidence_high=1.5)

    # Test 9: confidence_low > confidence_high
    with pytest.raises(ValueError, match="Seuils invalides"):
        FeedbackLoopConfig(confidence_low=0.9, confidence_high=0.8)

    # Test 10: suggestion_threshold >= auto_threshold
    with pytest.raises(ValueError, match="suggestion_threshold .* doit être"):
        FeedbackLoopConfig(suggestion_threshold=5, auto_threshold=3)


def test_types_query_context():
    """Type QueryContext valide."""
    ctx: QueryContext = {
        "query": "test",
        "session_id": "123",
        "rag_score": 0.85,
        "last_mcp": "vm_start",
        "frequent_mcp": "vm_clone",
    }

    assert ctx["query"] == "test"
    assert ctx["session_id"] == "123"
    assert ctx["rag_score"] == 0.85
    assert ctx["last_mcp"] == "vm_start"
    assert ctx["frequent_mcp"] == "vm_clone"

    # Test avec valeurs optionnelles None
    ctx2: QueryContext = {
        "query": "test2",
        "session_id": "456",
        "rag_score": 0.60,
    }
    assert ctx2["query"] == "test2"


def test_types_rag_result():
    """Type RAGResult valide."""
    result: RAGResult = {
        "tool_name": "vm_start",
        "confidence": 0.90,
        "source": "registry",
        "metadata": {"server": "fedora"},
    }

    assert result["tool_name"] == "vm_start"
    assert result["confidence"] == 0.90
    assert result["source"] == "registry"
    assert result["metadata"]["server"] == "fedora"

    # Test sources valides
    result2: RAGResult = {
        "tool_name": "vm_clone",
        "confidence": 0.75,
        "source": "capabilities",
        "metadata": {},
    }
    assert result2["source"] == "capabilities"

    result3: RAGResult = {
        "tool_name": "vm_snapshot",
        "confidence": 0.65,
        "source": "parameters",
        "metadata": {},
    }
    assert result3["source"] == "parameters"


def test_types_enums():
    """Test des Enums."""
    # ConfidenceLevel
    assert ConfidenceLevel.HIGH.value == "high"
    assert ConfidenceLevel.MEDIUM.value == "medium"
    assert ConfidenceLevel.LOW.value == "low"

    # CascadeAction
    assert CascadeAction.EXECUTE.value == "execute"
    assert CascadeAction.PROPOSE.value == "propose"
    assert CascadeAction.FALLBACK.value == "fallback"


def test_constants():
    """Test des constantes."""
    from lyra.rag_enhanced.constants import (
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

    # Seuils confiance (M2 - mis a jour)
    assert CONFIDENCE_HIGH == 0.80
    assert CONFIDENCE_MEDIUM == 0.50
    assert CONFIDENCE_LOW == 0.50

    # Limites slang
    assert SLANG_MAX_PATTERNS == 200

    # Limites synonym
    assert SYNONYM_MAX_PER_KEYWORD == 6
    assert SYNONYM_MAX_TOKENS_ADDED == 15

    # Limites contexte
    assert CONTEXT_DEFAULT_WINDOW == 5
    assert CONTEXT_MAX_WINDOW == 15
    assert CONTEXT_FIFO_LIMIT == 15


def test_config_from_yaml_integration(tmp_path, sample_config_dict):
    """Test chargement depuis fichier YAML réel."""
    # Créer fichier YAML temporaire
    yaml_path = tmp_path / "test_config.yaml"
    with open(yaml_path, "w") as f:
        yaml.dump({"rag_enhanced": sample_config_dict}, f)

    # Charger
    with open(yaml_path, "r") as f:
        data = yaml.safe_load(f)

    config = RAGEnhancedConfig.from_dict(data["rag_enhanced"])

    assert config.enabled is True
    assert config.slang_normalizer.enabled is True
    assert config.synonym_expander.max_synonyms == 6


def test_config_partial_dict():
    """Test chargement depuis dict partiel (valeurs par défaut)."""
    partial_dict = {
        "enabled": True,
        "slang_normalizer": {
            "enabled": True,
            # Pas de max_patterns -> utilise défaut
        },
    }

    config = RAGEnhancedConfig.from_dict(partial_dict)

    assert config.enabled is True
    assert config.slang_normalizer.enabled is True
    assert config.slang_normalizer.max_patterns == SLANG_MAX_PATTERNS  # Défaut
    assert config.synonym_expander.enabled is False  # Défaut


def test_config_immutability_after_validation():
    """Test que la validation se fait au __post_init__."""
    # Config valide
    config = SlangNormalizerConfig(max_patterns=100)
    assert config.max_patterns == 100

    # Si on essaie de modifier après (pas recommandé mais possible avec dataclass)
    # On ne peut pas re-valider automatiquement, c'est un limitation acceptée
    # pour les dataclasses Python


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
