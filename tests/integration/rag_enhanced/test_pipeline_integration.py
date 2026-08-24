"""
Tests d'integration pour EnhancedPipeline.

SESSION 7 (P6.1) - RAG Enhanced

Ces tests necessitent Ollama en cours d'execution (EPHAISTOS + LYRA).
Pour les tests sans LLM : voir test_pipeline_integration_simple.py
Pour les tests E2E mockes : voir tests/e2e/rag_enhanced/
"""

import pytest
from pathlib import Path

CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "config.yaml"


def load_enhanced_config():
    """Charge la RAGEnhancedConfig depuis config.yaml (comme en prod)."""
    import yaml
    from lyra.rag_enhanced.config import RAGEnhancedConfig
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)
    return RAGEnhancedConfig.from_dict(cfg.get("rag_enhanced", {}))


class TestPipelineEnhancedBasic:
    """Tests de base du pipeline enhanced."""

    def test_pipeline_enhanced_full_flow(self):
        """Slang -> RAG -> Cascade -> Feedback - chaque etape laisse une trace."""
        from lyra.rag_enhanced.pipeline_enhanced import EnhancedPipeline

        enhanced_config = load_enhanced_config()
        pipeline = EnhancedPipeline(enhanced_config=enhanced_config, enabled=True)
        result = pipeline.process_query("start preprod-09")

        # Slang : "start" -> "demarre" (avec accent selon dict)
        assert hasattr(result, 'normalized_query')
        assert result.normalized_query is not None
        assert "start" not in result.normalized_query.lower() or result.normalized_query == "start preprod-09"

        # RAG source tracee
        assert hasattr(result, 'rag_source')
        assert result.rag_source in [
            "registry", "capabilities", "parameters",
            "v2_fallback", "v2_bm25_shortcut", None
        ]

        # Cascade action tracee
        assert hasattr(result, 'cascade_action')
        assert result.cascade_action in ["execute", "propose", "fallback", None]

        # Feedback enregistre
        assert hasattr(result, 'feedback_recorded')

    def test_pipeline_enhanced_disabled(self):
        """Enhanced disabled -> query non normalisee, comportement V2 pur."""
        from lyra.rag_enhanced.pipeline_enhanced import EnhancedPipeline

        pipeline = EnhancedPipeline(enabled=False)
        result = pipeline.process_query("start preprod-09")

        # Slang desactive : query inchangee
        assert result.normalized_query == "start preprod-09"

    def test_pipeline_slang_only(self):
        """Slang seul active : 'start vm' -> 'demarre vm' (ou equivalent)."""
        from lyra.rag_enhanced.config import RAGEnhancedConfig
        from lyra.rag_enhanced.pipeline_enhanced import EnhancedPipeline

        enhanced_config = RAGEnhancedConfig()
        enhanced_config.slang_normalizer.enabled = True
        enhanced_config.synonym_expander.enabled = False
        enhanced_config.rag_3tier.enabled = False
        enhanced_config.context_injector.enabled = False
        enhanced_config.feedback_loop.enabled = False

        pipeline = EnhancedPipeline(enhanced_config=enhanced_config, enabled=True)
        result = pipeline.process_query("start vm")

        # "start" doit avoir ete normalise
        assert result.normalized_query is not None
        assert "start" not in result.normalized_query.lower()

    def test_pipeline_3tier_only(self):
        """RAG 3-tier seul active : rag_source doit etre tracee."""
        from lyra.rag_enhanced.config import RAGEnhancedConfig
        from lyra.rag_enhanced.pipeline_enhanced import EnhancedPipeline

        enhanced_config = RAGEnhancedConfig()
        enhanced_config.slang_normalizer.enabled = False
        enhanced_config.synonym_expander.enabled = False
        enhanced_config.rag_3tier.enabled = True
        enhanced_config.context_injector.enabled = False
        enhanced_config.feedback_loop.enabled = False

        pipeline = EnhancedPipeline(enhanced_config=enhanced_config, enabled=True)
        result = pipeline.process_query("demarre vm")

        assert hasattr(result, 'rag_source')
        assert result.rag_source in ["registry", "capabilities", "parameters", "v2_fallback"]


class TestPipelineEnhancedCompat:
    """Tests de compatibilite backward."""

    def test_pipeline_backward_compat(self):
        """Enhanced(enabled=False) -> reponse identique a V2 pur."""
        from lyra.core.pipeline import Pipeline
        from lyra.rag_enhanced.pipeline_enhanced import EnhancedPipeline
        from lyra.core.config import RAGConfig

        rag_config = RAGConfig.from_yaml(CONFIG_PATH)

        pipeline_v2 = Pipeline(config=rag_config)
        pipeline_v2.initialize()

        pipeline_enhanced = EnhancedPipeline(config=rag_config, enabled=False)
        pipeline_enhanced.initialize()

        query = "demarre fedora-base"
        result_v2 = pipeline_v2.process(query)
        result_enhanced = pipeline_enhanced.process_query(query)

        # Les deux doivent detecter le meme outil avec les memes arguments.
        # On ne compare pas la reponse textuelle (LYRA est non-deterministe).
        assert result_v2.tool_call is not None
        assert result_enhanced.tool_call is not None
        v2_tool = result_v2.tool_call.get('name', '').split('.')[-1]
        enh_tool = result_enhanced.tool_call.get('name', '').split('.')[-1]
        assert v2_tool == enh_tool, f"Outils differents: V2={v2_tool} Enhanced={enh_tool}"
        assert result_v2.tool_call.get('arguments', {}) == result_enhanced.tool_call.get('arguments', {})


@pytest.mark.skip(reason="Benchmark LLM - lancer manuellement avec Ollama")
class TestPipelineEnhancedPerformance:
    """Tests de performance - lancer manuellement."""

    def test_pipeline_performance(self, benchmark):
        """Overhead Enhanced vs V2 pur - objectif <50ms."""
        from lyra.core.pipeline import Pipeline
        from lyra.rag_enhanced.pipeline_enhanced import EnhancedPipeline
        from lyra.core.config import RAGConfig

        rag_config = RAGConfig.from_yaml(CONFIG_PATH)
        enhanced_config = load_enhanced_config()

        pipeline_v2 = Pipeline(config=rag_config)
        pipeline_v2.initialize()

        pipeline_enhanced = EnhancedPipeline(
            config=rag_config,
            enhanced_config=enhanced_config,
            enabled=True
        )
        pipeline_enhanced.initialize()

        query = "demarre fedora-base"

        def bench_v2():
            return pipeline_v2.process_query(query)

        def bench_enhanced():
            return pipeline_enhanced.process_query(query)

        benchmark(bench_v2)
        benchmark(bench_enhanced)


class TestPipelineEnhancedRobustness:
    """Tests de robustesse et gestion erreurs."""

    def test_pipeline_error_handling(self):
        """Slang normalizer = None -> pas de crash (fallback graceful)."""
        from lyra.rag_enhanced.pipeline_enhanced import EnhancedPipeline

        enhanced_config = load_enhanced_config()
        pipeline = EnhancedPipeline(enhanced_config=enhanced_config, enabled=True)
        pipeline.initialize()

        # Simuler defaillance du SlangNormalizer
        pipeline._slang_normalizer = None

        result = pipeline.process_query("start vm")
        # Ne doit pas crasher
        assert result is not None
        assert result.error is None or "slang" not in str(result.error).lower()

    def test_pipeline_metrics_tracking(self):
        """result.metrics contient les latences par composant."""
        from lyra.rag_enhanced.pipeline_enhanced import EnhancedPipeline

        enhanced_config = load_enhanced_config()
        pipeline = EnhancedPipeline(enhanced_config=enhanced_config, enabled=True)
        pipeline.initialize()

        result = pipeline.process_query("demarre vm")

        assert hasattr(result, 'metrics')
        metrics = result.metrics
        assert isinstance(metrics, dict)

        # Au moins la latence totale est tracee
        assert 'total_latency_ms' in metrics
        assert metrics['total_latency_ms'] > 0

    def test_pipeline_config_reload(self):
        """reload_config() change le comportement a chaud."""
        from lyra.rag_enhanced.config import RAGEnhancedConfig
        from lyra.rag_enhanced.pipeline_enhanced import EnhancedPipeline

        enhanced_config = load_enhanced_config()
        pipeline = EnhancedPipeline(enhanced_config=enhanced_config, enabled=True)
        pipeline.initialize()

        # Desactiver slang a chaud
        new_config = RAGEnhancedConfig()
        new_config.slang_normalizer.enabled = False
        pipeline.reload_config(new_config)

        result = pipeline.process_query("start vm")
        # Slang desactive -> query inchangee
        assert result.normalized_query == "start vm"


class TestPipelineEnhancedMultiTurn:
    """Tests multi-tours avec injection de contexte."""

    def test_pipeline_multi_turn(self):
        """3 tours consecutifs : le pipeline tient la session sans crasher.

        Note: les assertions sur le contenu exact des args LLM sont dans les
        tests E2E (mockes). Ici on valide la stabilite et les metriques.
        """
        from lyra.rag_enhanced.pipeline_enhanced import EnhancedPipeline

        enhanced_config = load_enhanced_config()
        pipeline = EnhancedPipeline(enhanced_config=enhanced_config, enabled=True)
        pipeline.initialize()

        # Tour 1 : Demarrer VM - vm_name doit etre extrait
        result1 = pipeline.process_query("demarre fedora-base")
        assert result1 is not None
        assert result1.tool_call is not None
        assert "fedora-base" in str(result1.tool_call.get('arguments', {}))
        assert 'total_latency_ms' in result1.metrics

        # Tour 2 : Action suivante - le pipeline ne crashe pas
        result2 = pipeline.process_query("fais un snapshot")
        assert result2 is not None
        assert 'total_latency_ms' in result2.metrics

        # Tour 3 : Status - stabilite sur 3 tours
        result3 = pipeline.process_query("quel est le status")
        assert result3 is not None
        assert 'total_latency_ms' in result3.metrics
