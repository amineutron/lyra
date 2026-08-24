"""
Lyra Core - Fast path par regles statiques.

Detection d'une requete via les regles (lyra/rules) SANS initialiser le RAG.
Extrait de main_rag.py pour etre partage entre le CLI historique et le demon.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def try_fast_path_rules(query: str):
    """Tente de matcher la query via regles statiques SANS initialiser le RAG.

    Applique la normalisation slang (pure Python, <1ms) puis teste les regles.
    Si un match est trouve, retourne l'EphaistosAnalysis directement —
    ce qui permet d'utiliser initialize_fast() et de skipper SentenceTransformer,
    ChromaDB, IntentClassifier LLM et EPHAISTOS LLM.

    Returns:
        EphaistosAnalysis si regle matchee, None sinon
    """
    try:
        from lyra.core.formatters import enrich_optional_args
        from lyra.rules import detect

        # Normalisation slang (pure Python, aucune dep lourde)
        normalized = query
        try:
            from lyra.rag_enhanced.slang_normalizer import get_default_normalizer
            normalized = get_default_normalizer().normalize(query)
        except ImportError:
            pass  # Module optionnel absent, continuer avec la query originale
        except Exception as e:
            logger.warning("slang_normalizer failed: %s", e)

        # Tester query normalisee d'abord, puis originale si differente
        candidates = [normalized, query] if normalized != query else [query]
        for q in candidates:
            analysis = detect(q)
            if analysis is not None:
                return enrich_optional_args(q, analysis)
        return None
    except ImportError:
        pass  # Module rules absent, fallback sur le pipeline complet
    except Exception as e:
        logger.warning("fast_path_rules failed: %s", e)
    return None
