"""
Tests unitaires pour ContextInjector.

SESSION 4 (P3) - RAG Enhanced
Mis a jour pour API SessionMemory (sans SQLite).
"""

import pytest

from lyra.rag_enhanced.context_injector import ContextInjector


class MockTurn:
    """Tour de conversation simule."""

    def __init__(self, tool_call=None):
        self.tool_call = tool_call


class MockSessionMemory:
    """SessionMemory simulee pour les tests."""

    def __init__(self):
        self._history = []

    def add_turn(self, tool_call=None):
        self._history.append(MockTurn(tool_call=tool_call))


class TestContextInjector:
    """Tests pour l'injecteur de contexte."""

    def test_should_inject_large_gap(self):
        """Test : Ecart >0.10 → pas besoin contexte"""
        injector = ContextInjector()

        rag_results = [
            {'tool_name': 'vm_start', 'score': 0.90},
            {'tool_name': 'vm_clone', 'score': 0.70}
        ]

        should_inject, n = injector.should_inject(rag_results)

        # Ecart 0.20 > 0.10 → pas besoin contexte
        assert should_inject is False
        assert n == 0

    def test_should_inject_medium_gap(self):
        """Test : Ecart 0.05-0.10 → inject 5 echanges"""
        injector = ContextInjector()

        rag_results = [
            {'tool_name': 'vm_start', 'score': 0.75},
            {'tool_name': 'vm_clone', 'score': 0.68}
        ]

        should_inject, n = injector.should_inject(rag_results)

        # Ecart 0.07, ambiguite moderee
        assert should_inject is True
        assert n == 5

    def test_should_inject_small_gap(self):
        """Test : Ecart <0.05 → inject 10 echanges (ambiguite forte)"""
        injector = ContextInjector()

        rag_results = [
            {'tool_name': 'backup_create', 'score': 0.72},
            {'tool_name': 'vm_snapshot', 'score': 0.70}
        ]

        should_inject, n = injector.should_inject(rag_results)

        # Ecart 0.02 < 0.05 → ambiguite forte
        assert should_inject is True
        assert n == 10

    def test_inject_context_with_history(self):
        """Test : Injection contexte depuis historique session"""
        injector = ContextInjector()

        # Creer SessionMemory simulee avec historique
        session_memory = MockSessionMemory()
        session_memory.add_turn(tool_call=None)  # tour user sans MCP
        session_memory.add_turn(
            tool_call={'name': 'fedora.vm_start', 'arguments': {'vm_name': 'preprod-09'}}
        )

        query = "fais un snapshot"
        result = injector.inject(query, session_memory, n=5)

        # Contexte doit etre injecte
        assert "[ctx:" in result
        assert "last_mcp=fedora.vm_start" in result
        assert "last_server=FEDORA" in result
        assert "last_vm=preprod-09" in result

    def test_inject_frequent_mcp(self):
        """Test : Extrait MCP frequent"""
        injector = ContextInjector()

        # Historique avec fedora.vm_start frequent
        session_memory = MockSessionMemory()
        session_memory.add_turn(
            tool_call={'name': 'fedora.vm_start', 'arguments': {}}
        )
        session_memory.add_turn(
            tool_call={'name': 'fedora.vm_start', 'arguments': {}}
        )
        session_memory.add_turn(
            tool_call={'name': 'fedora.vm_clone', 'arguments': {}}
        )

        result = injector.inject("query", session_memory, n=5)

        # frequent_mcp doit etre fedora.vm_start (le plus frequent)
        assert "frequent_mcp=fedora.vm_start" in result

    def test_disabled_injector(self):
        """Test : Config enabled=false → pas d'injection"""
        injector = ContextInjector(enabled=False)

        session_memory = MockSessionMemory()
        session_memory.add_turn(
            tool_call={'name': 'fedora.vm_start', 'arguments': {}}
        )

        query = "fais un snapshot"
        result = injector.inject(query, session_memory, n=5)

        # Doit retourner query inchangee
        assert result == query
        assert "[ctx:" not in result


class TestContextInjectorEdgeCases:
    """Tests pour les edge cases."""

    def test_single_rag_result(self):
        """Test : 1 seul resultat RAG → pas d'injection"""
        injector = ContextInjector()

        rag_results = [
            {'tool_name': 'vm_start', 'score': 0.90}
        ]

        should_inject, n = injector.should_inject(rag_results)

        # Pas assez de resultats pour comparer
        assert should_inject is False
        assert n == 0

    def test_empty_history(self):
        """Test : Historique vide → query inchangee"""
        injector = ContextInjector()

        session_memory = MockSessionMemory()  # Historique vide

        query = "demarre vm"
        result = injector.inject(query, session_memory, n=5)

        # Retourne query inchangee si pas d'historique
        assert result == query
        assert "[ctx:" not in result

    def test_history_without_mcp(self):
        """Test : Historique sans MCP → query inchangee"""
        injector = ContextInjector()

        session_memory = MockSessionMemory()
        session_memory.add_turn(tool_call=None)  # Discussion sans MCP
        session_memory.add_turn(tool_call=None)  # Discussion sans MCP

        result = injector.inject("demarre vm", session_memory, n=5)

        # Contexte tout None → pas d'injection
        assert result == "demarre vm"
        assert "[ctx:" not in result

    def test_boundary_gap_high(self):
        """Test : Ecart exactement 0.10 → ambiguite moderee"""
        injector = ContextInjector()

        rag_results = [
            {'tool_name': 'vm_start', 'score': 0.80},
            {'tool_name': 'vm_clone', 'score': 0.70}
        ]

        should_inject, n = injector.should_inject(rag_results)

        # Ecart = 0.10, boundary → traite comme >= 0.05
        assert should_inject is True
        assert n == 5

    def test_boundary_gap_low(self):
        """Test : Ecart exactement 0.05 → ambiguite moderee"""
        injector = ContextInjector()

        rag_results = [
            {'tool_name': 'vm_start', 'score': 0.75},
            {'tool_name': 'vm_clone', 'score': 0.70}
        ]

        should_inject, n = injector.should_inject(rag_results)

        # Ecart = 0.05, boundary → inject 5
        assert should_inject is True
        assert n == 5

    def test_very_small_gap(self):
        """Test : Ecart 0.01 → inject 10 echanges"""
        injector = ContextInjector()

        rag_results = [
            {'tool_name': 'backup_create', 'score': 0.71},
            {'tool_name': 'vm_snapshot', 'score': 0.70}
        ]

        should_inject, n = injector.should_inject(rag_results)

        # Ecart 0.01 << 0.05
        assert should_inject is True
        assert n == 10

    def test_inject_extracts_server(self):
        """Test : Extrait le serveur du nom d'outil (format server.tool)"""
        injector = ContextInjector()

        session_memory = MockSessionMemory()
        session_memory.add_turn(
            tool_call={'name': 'fedora.vm_start', 'arguments': {'vm_name': 'preprod-09'}}
        )

        result = injector.inject("fais un snapshot", session_memory, n=5)

        assert "[ctx:" in result
        assert "last_mcp=fedora.vm_start" in result
        assert "last_server=FEDORA" in result
        assert "last_vm=preprod-09" in result


class TestContextInjectorIntegration:
    """Tests d'integration."""

    def test_full_workflow(self):
        """Test : Workflow complet injection contexte"""
        injector = ContextInjector()

        session_memory = MockSessionMemory()

        # Ecart faible → injection necessaire
        rag_results = [
            {'tool_name': 'vm_snapshot', 'score': 0.72},
            {'tool_name': 'backup_create', 'score': 0.70}
        ]
        should_inject, n = injector.should_inject(rag_results)
        assert should_inject is True
        assert n == 10  # Ecart 0.02 < 0.05

        # Simuler historique apres action precedente
        session_memory.add_turn(
            tool_call={'name': 'fedora.vm_start', 'arguments': {'vm_name': 'preprod-09'}}
        )

        # Injecter contexte
        query = "fais un backup"
        enriched = injector.inject(query, session_memory, n=n)

        assert "[ctx:" in enriched
        assert "last_mcp=fedora.vm_start" in enriched
        assert "last_server=FEDORA" in enriched

    def test_inject_vm_from_source_vm(self):
        """Test : Extrait VM depuis source_vm"""
        injector = ContextInjector()

        session_memory = MockSessionMemory()
        session_memory.add_turn(
            tool_call={
                'name': 'fedora.vm_clone',
                'arguments': {'source_vm': 'preprod-09', 'new_vm_name': 'test-clone'}
            }
        )

        result = injector.inject("snapshot", session_memory)

        # Doit extraire source_vm en priorite
        assert "last_vm=preprod-09" in result

    def test_enabled_default(self):
        """Test : ContextInjector active par defaut"""
        injector = ContextInjector()

        assert injector.enabled is True

    def test_disabled_init(self):
        """Test : ContextInjector desactive a l'init"""
        injector = ContextInjector(enabled=False)

        assert injector.enabled is False
