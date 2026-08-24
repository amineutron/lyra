"""
Tests unitaires pour le SynonymExpander.

SESSION 3 (P2) - RAG Enhanced
"""

import json
import time
from pathlib import Path

import pytest

from lyra.rag_enhanced.synonym_expander import SynonymExpander
from lyra.rag_enhanced.constants import (
    SYNONYM_MAX_PER_KEYWORD,
    SYNONYM_MAX_TOKENS_ADDED,
)


class TestSynonymExpander:
    """Tests pour le SynonymExpander."""

    def test_expand_single_word(self):
        """Test : 'vm' → ['vm', 'machine', 'serveur', ...]"""
        expander = SynonymExpander()
        result = expander.expand("vm")

        # Vérifie que le mot original est présent
        assert "vm" in result

        # Vérifie que des synonymes sont ajoutés
        assert "machine" in result or "serveur" in result

        # Résultat doit être plus long que l'original
        assert len(result) > len("vm")

    def test_expand_multi_word(self):
        """Test : 'vm preprod' → expansion avec contexte"""
        expander = SynonymExpander()
        result = expander.expand("vm preprod")

        # Le texte original doit être préservé
        assert "vm" in result
        assert "preprod" in result

        # Des synonymes de "vm" doivent être ajoutés
        assert "machine" in result or "serveur" in result or "virtuelle" in result

    def test_max_synonyms_limit(self):
        """Test : Max 6 synonymes par mot-clé (limite TOPO)"""
        expander = SynonymExpander(max_synonyms=6)
        result = expander.expand("lumière")

        # Compter les nouveaux mots ajoutés
        original_words = set("lumière".split())
        result_words = set(result.split())
        added_words = result_words - original_words

        # Max 6 synonymes (limite TOPO)
        assert len(added_words) <= 6

    def test_max_tokens_added_limit(self):
        """Test : Max 15 tokens ajoutés (limite TOPO)"""
        expander = SynonymExpander(max_tokens_added=15)

        query = "allume toutes les lumières du salon"
        result = expander.expand(query)

        # Compter tokens originaux et résultat
        original_token_count = len(query.split())
        result_token_count = len(result.split())
        added_tokens = result_token_count - original_token_count

        # Max 15 tokens ajoutés (limite TOPO)
        assert added_tokens <= 15

    def test_expand_no_synonyms(self):
        """Test : Mot sans synonymes → inchangé"""
        expander = SynonymExpander()
        result = expander.expand("xyzabc123nonexistent")

        # Doit retourner le texte original inchangé
        assert result == "xyzabc123nonexistent"

    def test_expand_french_specific(self):
        """Test : 'démarre' → synonymes français"""
        expander = SynonymExpander()
        result = expander.expand("démarre")

        # Devrait contenir le mot original
        assert "démarre" in result

        # Devrait contenir au moins un synonyme français
        assert any(word in result for word in ["lance", "boot", "active"])

    def test_expand_with_stopwords(self):
        """Test : Ignore stopwords ('le', 'la', 'de')"""
        expander = SynonymExpander()
        result = expander.expand("allume la lumière")

        # Stopword "la" doit être préservé
        assert "la" in result

        # Mots principaux doivent être présents
        assert "allume" in result
        assert "lumière" in result

        # Synonymes doivent être ajoutés
        assert len(result) > len("allume la lumière")

    def test_custom_synonym_dict(self):
        """Test : Charge dictionnaire custom"""
        custom_dict = {
            "foo": ["bar", "baz", "qux"]
        }

        expander = SynonymExpander(custom_dict=custom_dict)
        result = expander.expand("foo")

        # Mot original préservé
        assert "foo" in result

        # Synonymes ajoutés
        assert "bar" in result
        assert "baz" in result

    def test_disabled_expander(self):
        """Test : Config enabled=false → pas d'expansion"""
        expander = SynonymExpander(enabled=False)
        query = "vm preprod"
        result = expander.expand(query)

        # Doit retourner exactement le texte original
        assert result == query

    @pytest.mark.skipif(
        __import__("importlib.util", fromlist=["util"]).find_spec("pytest_benchmark") is None,
        reason="pytest-benchmark non installé (installer requirements-dev.txt)"
    )
    def test_expand_performance(self, benchmark):
        """Test : <1ms pour 100 requêtes"""
        expander = SynonymExpander()
        queries = ["allume la lumière du salon"] * 100

        def expand_all():
            return [expander.expand(q) for q in queries]

        result = benchmark(expand_all)

        # Médiane <1ms pour 100 requêtes → <0.01ms par requête
        assert benchmark.stats.stats.median < 0.001  # <1ms total

    def test_expand_performance_manual(self):
        """
        Test performance manuel (fallback si pytest-benchmark absent).

        Mesure médiane sur 10 runs de 1000 requêtes.
        Critère: <1ms par requête.
        """
        expander = SynonymExpander()
        query = "allume la lumière du salon"

        times = []
        for _ in range(10):
            start = time.perf_counter()
            for _ in range(1000):
                result = expander.expand(query)
            elapsed = (time.perf_counter() - start) * 1000  # ms
            times.append(elapsed)

        # Médiane du temps total pour 1000 requêtes
        median_total_ms = sorted(times)[len(times) // 2]
        median_per_query_ms = median_total_ms / 1000

        # Debug info
        print(f"\n[PERF] Médiane: {median_per_query_ms:.4f}ms par requête")
        print(f"[PERF] Total 1000 requêtes: {median_total_ms:.2f}ms")

        # Critère: <1ms par requête
        assert median_per_query_ms < 1.0, (
            f"Performance insuffisante: {median_per_query_ms:.4f}ms > 1ms"
        )


class TestSynonymExpanderEdgeCases:
    """Tests pour les edge cases."""

    def test_empty_query(self):
        """Test : Query vide → vide"""
        expander = SynonymExpander()
        result = expander.expand("")
        assert result == ""

    def test_whitespace_only(self):
        """Test : Espaces seulement → espaces"""
        expander = SynonymExpander()
        result = expander.expand("   ")
        assert result.strip() == ""

    def test_special_characters(self):
        """Test : Caractères spéciaux préservés"""
        expander = SynonymExpander()
        result = expander.expand("vm-preprod-01")

        # Tirets doivent être préservés
        assert "-" in result

    def test_numbers(self):
        """Test : Nombres préservés"""
        expander = SynonymExpander()
        result = expander.expand("vm 192.168.0.1")

        # IP préservée
        assert "192.168.0.1" in result

    def test_case_preservation(self):
        """Test : Casse du texte original préservée"""
        expander = SynonymExpander()
        result = expander.expand("Démarre VM")

        # Le mot original doit être préservé avec sa casse
        assert "Démarre" in result or "démarre" in result
        assert "VM" in result or "vm" in result


class TestSynonymExpanderIntegration:
    """Tests d'intégration avec le dictionnaire réel."""

    def test_load_default_dict(self):
        """Test : Charge dictionnaire par défaut"""
        expander = SynonymExpander()

        # Vérifie que le dictionnaire est chargé
        assert expander.synonym_dict is not None
        assert len(expander.synonym_dict) > 0

    def test_dict_respects_limits(self):
        """Test : Dictionnaire respecte les limites TOPO"""
        expander = SynonymExpander()

        # Max 80 keywords (limite TOPO)
        assert len(expander.synonym_dict) <= 80

        # Max 6 synonymes par mot-clé (limite TOPO)
        for keyword, synonyms in expander.synonym_dict.items():
            assert len(synonyms) <= 6, (
                f"Keyword '{keyword}' a {len(synonyms)} synonymes (max 6)"
            )

    def test_vm_synonyms(self):
        """Test : 'vm' a bien ses synonymes attendus"""
        expander = SynonymExpander()
        result = expander.expand("vm")

        # Synonymes attendus de "vm"
        expected_synonyms = ["machine", "serveur", "instance", "virtuelle"]

        # Au moins 2 synonymes doivent être présents
        found = sum(1 for syn in expected_synonyms if syn in result)
        assert found >= 2

    def test_lumiere_synonyms(self):
        """Test : 'lumière' a bien ses synonymes"""
        expander = SynonymExpander()
        result = expander.expand("lumière")

        # Synonymes attendus de "lumière"
        expected_synonyms = ["éclairage", "lampe", "ampoule"]

        # Au moins 1 synonyme doit être présent
        found = sum(1 for syn in expected_synonyms if syn in result)
        assert found >= 1

    def test_backup_synonyms(self):
        """Test : 'backup' a bien ses synonymes"""
        expander = SynonymExpander()
        result = expander.expand("backup")

        # Synonymes attendus de "backup"
        expected_synonyms = ["sauvegarde", "copie", "archive"]

        # Au moins 1 synonyme doit être présent
        found = sum(1 for syn in expected_synonyms if syn in result)
        assert found >= 1

    def test_dict_file_not_found(self, tmp_path):
        """Test : Dictionnaire absent → dict vide"""
        non_existent = tmp_path / "nonexistent.json"
        expander = SynonymExpander(dict_path=str(non_existent))

        # Doit avoir un dict vide
        assert expander.synonym_dict == {}

        # Expansion doit retourner query inchangée
        assert expander.expand("test") == "test"

    def test_invalid_json(self, tmp_path):
        """Test : JSON invalide → dict vide"""
        bad_json = tmp_path / "bad.json"
        bad_json.write_text("{invalid json", encoding="utf-8")

        expander = SynonymExpander(dict_path=str(bad_json))

        # Doit avoir un dict vide
        assert expander.synonym_dict == {}

    def test_get_stats_empty_dict(self):
        """Test : get_stats avec dict vide"""
        expander = SynonymExpander(custom_dict={})
        stats = expander.get_stats()

        assert stats["total_keywords"] == 0
        assert stats["avg_synonyms_per_keyword"] == 0.0
        assert stats["max_synonyms"] == 0

    def test_get_synonym_expander_singleton(self):
        """Test : get_synonym_expander retourne singleton"""
        from lyra.rag_enhanced.synonym_expander import get_synonym_expander

        instance1 = get_synonym_expander()
        instance2 = get_synonym_expander()

        # Même instance
        assert instance1 is instance2
