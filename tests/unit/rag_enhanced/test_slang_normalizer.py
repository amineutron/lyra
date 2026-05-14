"""
Tests unitaires pour le Slang Normalizer.
"""

import pytest
import json
import time
from pathlib import Path

from lyra.rag_enhanced.slang_normalizer import SlangNormalizer

# Vérifier si pytest-benchmark est disponible
try:
    import pytest_benchmark
    BENCHMARK_AVAILABLE = True
except ImportError:
    BENCHMARK_AVAILABLE = False


class TestSlangNormalizer:
    """Tests pour SlangNormalizer."""

    def test_normalize_single_slang(self):
        """'start' → 'démarre'"""
        normalizer = SlangNormalizer()
        result = normalizer.normalize("start")
        assert result == "démarre"

    def test_normalize_multiple_slang(self):
        """'start la vm' → 'démarre la vm'"""
        normalizer = SlangNormalizer()
        result = normalizer.normalize("start la vm")
        assert result == "démarre la vm"

    def test_normalize_case_insensitive(self):
        """'START' → 'démarre'"""
        normalizer = SlangNormalizer()
        result = normalizer.normalize("START")
        assert result == "démarre"

        # Mixed case
        result2 = normalizer.normalize("Start la VM")
        assert result2 == "démarre la vm"  # Normalisé en minuscules

    def test_normalize_longest_match_first(self):
        """'backup manager' doit matcher avant 'backup' seul"""
        normalizer = SlangNormalizer()

        # "backup manager" doit être remplacé par "gestionnaire de sauvegarde"
        # PAS par "sauvegarde manager"
        result = normalizer.normalize("backup manager")
        assert "gestionnaire" in result
        assert result == "gestionnaire de sauvegarde"

        # "backup simple" doit être "sauvegarde simple"
        result2 = normalizer.normalize("backup simple")
        assert result2 == "sauvegarde simple"

    def test_normalize_no_slang(self):
        """'démarre vm' → 'démarre vm' (inchangé)"""
        normalizer = SlangNormalizer()
        result = normalizer.normalize("démarre vm")
        assert result == "démarre vm"

    @pytest.mark.skipif(not BENCHMARK_AVAILABLE, reason="pytest-benchmark not installed")
    def test_normalize_performance(self, benchmark):
        """<1ms pour 100 requêtes (avec pytest-benchmark)"""
        normalizer = SlangNormalizer()
        queries = ["start vm preprod-09"] * 100

        def normalize_batch():
            return [normalizer.normalize(q) for q in queries]

        result = benchmark(normalize_batch)

        # Vérifier que le benchmark a été exécuté
        assert len(result) == 100
        assert result[0] == "démarre vm preprod-09"

        # La mediane par requete doit etre <1ms
        # Note: benchmark.stats.stats.median est en secondes (pour 100 requetes)
        if hasattr(benchmark, 'stats'):
            median_seconds = benchmark.stats.stats.median
            median_ms_per_query = (median_seconds * 1000) / 100
            assert median_ms_per_query < 1.0, f"Mediane {median_ms_per_query:.3f}ms/requete >= 1ms"

    def test_normalize_performance_manual(self):
        """<1ms par requête (test manuel sans pytest-benchmark)"""
        normalizer = SlangNormalizer()
        query = "start vm preprod-09"

        # Mesurer temps pour 1000 requêtes
        times = []
        for _ in range(10):  # 10 runs de 1000 requêtes
            start = time.perf_counter()
            for _ in range(1000):
                result = normalizer.normalize(query)
            elapsed = (time.perf_counter() - start) * 1000  # ms total
            times.append(elapsed)

        # Temps médian pour 1000 requêtes
        median_total_ms = sorted(times)[len(times) // 2]

        # Temps par requête
        median_per_query_ms = median_total_ms / 1000

        # Vérifier résultat
        assert result == "démarre vm preprod-09"

        # Médiane doit être <1ms par requête
        assert median_per_query_ms < 1.0, f"Médiane {median_per_query_ms:.3f}ms >= 1ms par requête"

    def test_load_custom_dict(self):
        """Chargement dictionnaire externe"""
        custom_dict = {"foo": "bar", "hello": "bonjour"}
        normalizer = SlangNormalizer(custom_dict=custom_dict)

        result = normalizer.normalize("foo world")
        assert result == "bar world"

        result2 = normalizer.normalize("hello world")
        assert result2 == "bonjour world"

    def test_disabled_normalizer(self):
        """Config enabled=false → pas de normalisation"""
        normalizer = SlangNormalizer(enabled=False)
        result = normalizer.normalize("start vm")
        assert result == "start vm"  # Inchangé

    def test_normalize_multi_word_patterns(self):
        """Patterns multi-mots (ex: 'power on' → 'allume')"""
        normalizer = SlangNormalizer()

        result = normalizer.normalize("power on the tv")
        assert result == "allume the télé"  # "power on" → "allume", "tv" → "télé"

        result2 = normalizer.normalize("turn off the lights")
        assert "éteins" in result2  # "turn off" → "éteins"
        assert "lumières" in result2  # "lights" → "lumières"

    def test_normalize_preserves_word_boundaries(self):
        """Ne normalise que les mots complets (pas des sous-chaînes)"""
        normalizer = SlangNormalizer()

        # "cast" n'est plus dans le dict (retiré pour éviter la collision avec cast_scan)
        result1 = normalizer.normalize("cast video")
        assert "cast" in result1.lower()  # cast reste intact

        # "broadcast" ne doit pas être affecté par un éventuel pattern "cast"
        result2 = normalizer.normalize("broadcast")
        assert result2 == "broadcast"  # Inchangé

    def test_normalize_dict_loaded_from_file(self):
        """Charge dict depuis data/slang_dict.json"""
        normalizer = SlangNormalizer()

        # Vérifier que le dict par défaut est chargé
        assert normalizer.slang_dict is not None
        assert len(normalizer.slang_dict) > 0

        # Tester quelques patterns du dict
        assert normalizer.normalize("start") == "démarre"
        assert normalizer.normalize("stop") == "arrête"
        assert normalizer.normalize("backup") == "sauvegarde"

    def test_normalize_empty_string(self):
        """Chaîne vide → chaîne vide"""
        normalizer = SlangNormalizer()
        result = normalizer.normalize("")
        assert result == ""

    def test_normalize_special_characters(self):
        """Préserve ponctuation et caractères spéciaux"""
        normalizer = SlangNormalizer()

        result = normalizer.normalize("start! vm?")
        assert result == "démarre! vm?"

        result2 = normalizer.normalize("backup, restore, clone")
        assert "sauvegarde" in result2
        assert "restaure" in result2
        assert "duplique" in result2


class TestSlangNormalizerIntegration:
    """Tests d'intégration SlangNormalizer."""

    def test_integration_with_pipeline_query(self):
        """Test normalisation d'une vraie requête LYRA"""
        normalizer = SlangNormalizer()

        # Requête typique utilisateur
        queries = [
            ("start preprod-09", "démarre preprod-09"),
            ("stop all vms", "arrête all vms"),
            ("backup my server", "sauvegarde my serveur"),
            ("turn on the lights", "allume the lumières"),
            ("stream youtube video", "diffuse youtube vidéo"),
        ]

        for original, expected in queries:
            result = normalizer.normalize(original)
            # Vérifier que les mots clés ont été normalisés
            for word in expected.split():
                if word not in ["the", "my", "all"]:  # Skip articles
                    assert word in result, f"'{word}' manquant dans '{result}'"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
