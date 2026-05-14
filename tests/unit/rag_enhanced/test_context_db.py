"""
Tests unitaires pour ContextDB (SQLite).

SESSION 4 (P3) - RAG Enhanced
"""

import time
from pathlib import Path

import pytest

from lyra.rag_enhanced.context_db import ContextDB


class TestContextDB:
    """Tests pour la base de données de contexte."""

    def test_create_database(self, tmp_path):
        """Test : Crée schema SQLite correct"""
        db_path = tmp_path / "test_context.db"
        db = ContextDB(str(db_path))

        # Vérifie que la DB est créée
        assert db_path.exists()

        # Vérifie que la table existe
        cursor = db.conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='session_history'"
        )
        result = cursor.fetchone()
        assert result is not None
        assert result[0] == "session_history"

    def test_log_exchange(self, tmp_path):
        """Test : Stocke échange user/lyra dans DB"""
        db_path = tmp_path / "test_context.db"
        db = ContextDB(str(db_path))

        # Log échange user
        db.log_exchange(
            session_id="123",
            role="user",
            content="démarre preprod-09",
            mcp_used=None,
            server_used=None
        )

        # Log échange lyra
        db.log_exchange(
            session_id="123",
            role="lyra",
            content="VM démarrée",
            mcp_used="vm_start",
            server_used="FEDORA"
        )

        # Vérifie que les échanges sont stockés
        history = db.get_last_exchanges("123", n=10)
        assert len(history) == 2

        # Ordre chronologique inverse (plus récent en premier)
        assert history[0]['content'] == "VM démarrée"
        assert history[1]['content'] == "démarre preprod-09"

    def test_get_last_exchanges(self, tmp_path):
        """Test : Récupère les N derniers échanges"""
        db_path = tmp_path / "test_context.db"
        db = ContextDB(str(db_path))

        # Log 10 échanges
        for i in range(10):
            db.log_exchange("123", "user", f"query {i}", None, None)
            # Petit délai pour garantir l'ordre
            time.sleep(0.001)

        # Récupère les 5 derniers
        last_5 = db.get_last_exchanges("123", n=5)
        assert len(last_5) == 5

        # Plus récent en premier
        assert last_5[0]['content'] == "query 9"
        assert last_5[4]['content'] == "query 5"

    def test_fifo_limit_15(self, tmp_path):
        """Test : FIFO - max 15 échanges par session"""
        db_path = tmp_path / "test_context.db"
        db = ContextDB(str(db_path))

        # Log 20 échanges
        for i in range(20):
            db.log_exchange("123", "user", f"query {i}", None, None)

        # Récupère tous les échanges
        history = db.get_last_exchanges("123", n=100)

        # FIFO : max 15 conservés (limite TOPO)
        assert len(history) == 15

        # Plus récent conservé
        assert history[0]['content'] == "query 19"

        # Plus ancien conservé (query 5, car 0-4 purgés)
        assert history[14]['content'] == "query 5"

    def test_extract_last_mcp(self, tmp_path):
        """Test : Extrait dernier MCP utilisé"""
        db_path = tmp_path / "test_context.db"
        db = ContextDB(str(db_path))

        # Log échanges
        db.log_exchange("123", "user", "démarre vm", None, None)
        db.log_exchange("123", "lyra", "OK", "vm_start", "FEDORA")
        time.sleep(0.001)
        db.log_exchange("123", "user", "fais un snapshot", None, None)
        db.log_exchange("123", "lyra", "OK", "vm_snapshot", "FEDORA")

        # Récupère historique
        history = db.get_last_exchanges("123", n=10)

        # Extraire dernier MCP
        last_mcp = None
        for exchange in history:
            if exchange['mcp_used']:
                last_mcp = exchange['mcp_used']
                break

        assert last_mcp == "vm_snapshot"

    def test_extract_frequent_mcp(self, tmp_path):
        """Test : Extrait MCP le plus fréquent"""
        db_path = tmp_path / "test_context.db"
        db = ContextDB(str(db_path))

        # Log échanges avec vm_start fréquent
        db.log_exchange("123", "lyra", "OK", "vm_start", "FEDORA")
        time.sleep(0.001)
        db.log_exchange("123", "lyra", "OK", "vm_start", "FEDORA")
        time.sleep(0.001)
        db.log_exchange("123", "lyra", "OK", "vm_clone", "FEDORA")

        # Récupère historique
        history = db.get_last_exchanges("123", n=10)

        # Compter occurrences
        mcp_counts = {}
        for exchange in history:
            if exchange['mcp_used']:
                mcp_counts[exchange['mcp_used']] = mcp_counts.get(exchange['mcp_used'], 0) + 1

        # vm_start le plus fréquent (2 occurrences)
        frequent = max(mcp_counts.items(), key=lambda x: x[1])[0]
        assert frequent == "vm_start"


class TestContextDBEdgeCases:
    """Tests pour les edge cases."""

    def test_empty_session(self, tmp_path):
        """Test : Session sans historique → liste vide"""
        db_path = tmp_path / "test_context.db"
        db = ContextDB(str(db_path))

        history = db.get_last_exchanges("nonexistent", n=10)
        assert history == []

    def test_multiple_sessions(self, tmp_path):
        """Test : Plusieurs sessions indépendantes"""
        db_path = tmp_path / "test_context.db"
        db = ContextDB(str(db_path))

        # Session 1
        db.log_exchange("session1", "user", "query 1", None, None)

        # Session 2
        db.log_exchange("session2", "user", "query 2", None, None)

        # Récupérer historiques séparés
        history1 = db.get_last_exchanges("session1", n=10)
        history2 = db.get_last_exchanges("session2", n=10)

        assert len(history1) == 1
        assert len(history2) == 1
        assert history1[0]['content'] == "query 1"
        assert history2[0]['content'] == "query 2"

    def test_special_characters(self, tmp_path):
        """Test : Caractères spéciaux dans le contenu"""
        db_path = tmp_path / "test_context.db"
        db = ContextDB(str(db_path))

        content = "Query avec 'quotes', \"double quotes\", et émojis 🚀"
        db.log_exchange("123", "user", content, None, None)

        history = db.get_last_exchanges("123", n=1)
        assert history[0]['content'] == content

    def test_role_validation(self, tmp_path):
        """Test : Role doit être 'user' ou 'lyra'"""
        db_path = tmp_path / "test_context.db"
        db = ContextDB(str(db_path))

        # Role valide
        db.log_exchange("123", "user", "test", None, None)
        db.log_exchange("123", "lyra", "test", None, None)

        # Role invalide devrait échouer (constraint CHECK)
        with pytest.raises(Exception):  # sqlite3.IntegrityError
            db.log_exchange("123", "invalid_role", "test", None, None)

    def test_large_content(self, tmp_path):
        """Test : Contenu volumineux (>1000 chars)"""
        db_path = tmp_path / "test_context.db"
        db = ContextDB(str(db_path))

        # Contenu de 2000 caractères
        content = "x" * 2000
        db.log_exchange("123", "user", content, None, None)

        history = db.get_last_exchanges("123", n=1)
        assert len(history[0]['content']) == 2000

    def test_close_connection(self, tmp_path):
        """Test : Fermeture propre de la connexion"""
        db_path = tmp_path / "test_context.db"
        db = ContextDB(str(db_path))

        db.log_exchange("123", "user", "test", None, None)

        # Fermer connexion
        db.close()

        # Vérifier que la DB persiste
        assert db_path.exists()

        # Réouvrir et vérifier données
        db2 = ContextDB(str(db_path))
        history = db2.get_last_exchanges("123", n=10)
        assert len(history) == 1
        assert history[0]['content'] == "test"
        db2.close()
