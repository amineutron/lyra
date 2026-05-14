"""
Fixtures pytest pour les tests RAG Enhanced.
"""

import pytest
from pathlib import Path


@pytest.fixture
def sample_config_dict():
    """Configuration RAG Enhanced exemple."""
    return {
        "enabled": True,
        "slang_normalizer": {
            "enabled": True,
            "dict_path": "data/slang_dict.json",
            "max_patterns": 200,
            "log_normalizations": True,
        },
        "synonym_expander": {
            "enabled": True,
            "dict_path": "data/synonym_dict.json",
            "max_synonyms": 6,
            "max_tokens_added": 15,
        },
        "context_injector": {
            "enabled": True,
            "db_path": "data/session_history.db",
            "default_window": 5,
            "max_window": 15,
            "fifo_limit": 15,
            "cache_ttl": 3600,
        },
        "rag_3tier": {
            "enabled": False,
            "collections": [
                "lyra_mcp_registry_v3",
                "lyra_mcp_capabilities_v3",
                "lyra_mcp_parameters_v3",
            ],
            "cascade_strategy": "early_stop",
        },
        "feedback_loop": {
            "enabled": True,
            "confidence_high": 0.85,
            "confidence_low": 0.60,
            "suggestion_threshold": 3,
            "auto_threshold": 5,
        },
        "metrics": {
            "enabled": True,
            "log_path": "logs/rag_enhanced_metrics.jsonl",
        },
    }


@pytest.fixture
def minimal_config_dict():
    """Configuration minimale (tout disabled)."""
    return {
        "enabled": False,
    }


@pytest.fixture
def invalid_config_dict():
    """Configuration invalide (pour tests validation)."""
    return {
        "enabled": True,
        "slang_normalizer": {
            "max_patterns": -1,  # Invalide
        },
    }
