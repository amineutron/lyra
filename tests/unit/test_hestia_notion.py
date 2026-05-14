"""
Tests unitaires pour NotionLogger.
"""

import pytest
import sys
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from lyra.hestia.executor import ExecutionContext


class TestNotionLoggerImport:
    """Tests pour l'import de NotionLogger."""

    def test_import_without_notion_client(self):
        """Test quand notion-client n'est pas installe."""
        # Ce test verifie juste que le module peut etre importe
        # meme sans notion-client (grace au try/except)
        from lyra.hestia import notion_logger
        # NOTION_AVAILABLE sera False ou True selon l'installation
        assert hasattr(notion_logger, 'NOTION_AVAILABLE')


class TestNotionLogger:
    """Tests pour NotionLogger."""

    @pytest.fixture
    def context(self):
        """Contexte d'execution de test."""
        return ExecutionContext(
            user_query="demarre preprod-09",
            tool_name="vm_start",
            arguments={"vm_name": "preprod-09"},
            session_id="test-session"
        )

    @pytest.fixture
    def mock_notion_module(self):
        """Setup mock pour notion_client."""
        # Creer un mock pour le module notion_client
        mock_client_class = Mock()
        mock_client_instance = Mock()
        mock_client_class.return_value = mock_client_instance

        # Creer un faux module notion_client
        mock_notion_client = MagicMock()
        mock_notion_client.Client = mock_client_class

        # Injecter dans sys.modules AVANT d'importer notion_logger
        with patch.dict(sys.modules, {'notion_client': mock_notion_client}):
            # Re-importer le module pour qu'il utilise le mock
            import importlib
            import lyra.hestia.notion_logger as notion_module
            importlib.reload(notion_module)

            yield {
                'module': notion_module,
                'client_class': mock_client_class,
                'client': mock_client_instance
            }

            # Cleanup: re-importer avec l'etat original
            try:
                importlib.reload(notion_module)
            except:
                pass

    def test_init_missing_token(self, mock_notion_module):
        """Test d'init sans token."""
        NotionLogger = mock_notion_module['module'].NotionLogger

        with pytest.raises(ValueError, match="token"):
            NotionLogger(token=None, database_id="db-id")

    def test_init_missing_database_id(self, mock_notion_module):
        """Test d'init sans database_id."""
        NotionLogger = mock_notion_module['module'].NotionLogger

        with pytest.raises(ValueError, match="database_id"):
            NotionLogger(token="token", database_id=None)

    def test_init_both_missing(self, mock_notion_module):
        """Test d'init avec les deux manquants."""
        NotionLogger = mock_notion_module['module'].NotionLogger

        with pytest.raises(ValueError):
            NotionLogger(token=None, database_id=None)

    def test_init_success(self, mock_notion_module):
        """Test d'initialisation reussie."""
        NotionLogger = mock_notion_module['module'].NotionLogger
        mock_client_class = mock_notion_module['client_class']

        logger = NotionLogger(token="secret-token", database_id="db-123")

        mock_client_class.assert_called_once_with(auth="secret-token")
        assert logger._database_id == "db-123"
        assert logger._enabled is True

    def test_log_start_success(self, mock_notion_module, context):
        """Test de log_start reussi."""
        NotionLogger = mock_notion_module['module'].NotionLogger
        mock_client = mock_notion_module['client']
        mock_client.pages.create.return_value = {"id": "page-123"}

        logger = NotionLogger(token="token", database_id="db-id")
        result = logger.log_start(context)

        assert result is True
        mock_client.pages.create.assert_called_once()

        # Verifier les proprietes passees
        call_args = mock_client.pages.create.call_args
        kwargs = call_args.kwargs if call_args.kwargs else call_args[1]
        properties = kwargs.get('properties', {})

        assert "Tool" in properties
        assert "Status" in properties
        assert properties["Status"]["select"]["name"] == "En cours"

    def test_log_start_disabled(self, mock_notion_module, context):
        """Test de log_start quand desactive."""
        NotionLogger = mock_notion_module['module'].NotionLogger

        logger = NotionLogger(token="token", database_id="db-id")
        logger.disable()

        result = logger.log_start(context)

        assert result is False

    def test_log_start_error(self, mock_notion_module, context):
        """Test de log_start avec erreur."""
        NotionLogger = mock_notion_module['module'].NotionLogger
        mock_client = mock_notion_module['client']
        mock_client.pages.create.side_effect = Exception("API Error")

        logger = NotionLogger(token="token", database_id="db-id")
        result = logger.log_start(context)

        assert result is False

    def test_log_end_success(self, mock_notion_module, context):
        """Test de log_end reussi."""
        NotionLogger = mock_notion_module['module'].NotionLogger
        mock_client = mock_notion_module['client']
        mock_client.databases.query.return_value = {
            "results": [{"id": "page-123"}]
        }

        logger = NotionLogger(token="token", database_id="db-id")
        result = logger.log_end(
            context=context,
            success=True,
            result="VM demarree",
            duration_ms=1234.5
        )

        assert result is True
        mock_client.databases.query.assert_called_once()
        mock_client.pages.update.assert_called_once()

        # Verifier les proprietes de mise a jour
        call_args = mock_client.pages.update.call_args
        kwargs = call_args.kwargs if call_args.kwargs else call_args[1]
        properties = kwargs.get('properties', {})

        assert properties["Status"]["select"]["name"] == "OK"
        assert properties["Duration (ms)"]["number"] == 1234.5

    def test_log_end_failure_status(self, mock_notion_module, context):
        """Test de log_end avec statut echec."""
        NotionLogger = mock_notion_module['module'].NotionLogger
        mock_client = mock_notion_module['client']
        mock_client.databases.query.return_value = {
            "results": [{"id": "page-123"}]
        }

        logger = NotionLogger(token="token", database_id="db-id")
        logger.log_end(
            context=context,
            success=False,
            result="VM not found",
            duration_ms=50.0
        )

        call_args = mock_client.pages.update.call_args
        kwargs = call_args.kwargs if call_args.kwargs else call_args[1]
        properties = kwargs.get('properties', {})

        assert properties["Status"]["select"]["name"] == "Erreur"

    def test_log_end_no_page_found(self, mock_notion_module, context):
        """Test de log_end sans page existante."""
        NotionLogger = mock_notion_module['module'].NotionLogger
        mock_client = mock_notion_module['client']
        mock_client.databases.query.return_value = {"results": []}

        logger = NotionLogger(token="token", database_id="db-id")
        result = logger.log_end(
            context=context,
            success=True,
            result="OK",
            duration_ms=100.0
        )

        # Devrait retourner False car pas de page a mettre a jour
        assert result is False
        mock_client.pages.update.assert_not_called()

    def test_log_end_disabled(self, mock_notion_module, context):
        """Test de log_end quand desactive."""
        NotionLogger = mock_notion_module['module'].NotionLogger

        logger = NotionLogger(token="token", database_id="db-id")
        logger.disable()

        result = logger.log_end(
            context=context,
            success=True,
            result="OK",
            duration_ms=100.0
        )

        assert result is False

    def test_log_end_error(self, mock_notion_module, context):
        """Test de log_end avec erreur."""
        NotionLogger = mock_notion_module['module'].NotionLogger
        mock_client = mock_notion_module['client']
        mock_client.databases.query.side_effect = Exception("API Error")

        logger = NotionLogger(token="token", database_id="db-id")
        result = logger.log_end(
            context=context,
            success=True,
            result="OK",
            duration_ms=100.0
        )

        assert result is False

    def test_enable_disable(self, mock_notion_module):
        """Test de enable/disable."""
        NotionLogger = mock_notion_module['module'].NotionLogger

        logger = NotionLogger(token="token", database_id="db-id")

        assert logger._enabled is True

        logger.disable()
        assert logger._enabled is False

        logger.enable()
        assert logger._enabled is True

    def test_truncates_long_arguments(self, mock_notion_module):
        """Test que les arguments longs sont tronques."""
        NotionLogger = mock_notion_module['module'].NotionLogger
        mock_client = mock_notion_module['client']

        # Creer un contexte avec des arguments tres longs
        long_context = ExecutionContext(
            user_query="x" * 1000,  # Plus de 500 chars
            tool_name="test",
            arguments={"data": "y" * 3000}  # Plus de 2000 chars
        )

        logger = NotionLogger(token="token", database_id="db-id")
        logger.log_start(long_context)

        # Verifier que les valeurs sont tronquees
        call_args = mock_client.pages.create.call_args
        kwargs = call_args.kwargs if call_args.kwargs else call_args[1]
        properties = kwargs.get('properties', {})

        user_query = properties["User Query"]["rich_text"][0]["text"]["content"]
        arguments = properties["Arguments"]["rich_text"][0]["text"]["content"]

        assert len(user_query) <= 500
        assert len(arguments) <= 2000


class TestNotionLoggerIntegration:
    """Tests d'integration pour NotionLogger."""

    @pytest.fixture
    def mock_notion_module(self):
        """Setup mock pour notion_client."""
        mock_client_class = Mock()
        mock_client_instance = Mock()
        mock_client_class.return_value = mock_client_instance

        mock_notion_client = MagicMock()
        mock_notion_client.Client = mock_client_class

        with patch.dict(sys.modules, {'notion_client': mock_notion_client}):
            import importlib
            import lyra.hestia.notion_logger as notion_module
            importlib.reload(notion_module)

            yield {
                'module': notion_module,
                'client_class': mock_client_class,
                'client': mock_client_instance
            }

            try:
                importlib.reload(notion_module)
            except:
                pass

    def test_full_logging_workflow(self, mock_notion_module):
        """Test du workflow complet de logging."""
        NotionLogger = mock_notion_module['module'].NotionLogger
        mock_client = mock_notion_module['client']

        mock_client.pages.create.return_value = {"id": "page-123"}
        mock_client.databases.query.return_value = {
            "results": [{"id": "page-123"}]
        }

        logger = NotionLogger(token="token", database_id="db-id")

        context = ExecutionContext(
            user_query="demarre preprod-09",
            tool_name="vm_start",
            arguments={"vm_name": "preprod-09"}
        )

        # 1. Log start
        start_result = logger.log_start(context)
        assert start_result is True

        # 2. Simuler l'execution...

        # 3. Log end
        end_result = logger.log_end(
            context=context,
            success=True,
            result="VM preprod-09 demarree avec IP 192.168.122.10",
            duration_ms=3456.7
        )
        assert end_result is True

        # Verifier que les deux appels ont ete faits
        assert mock_client.pages.create.call_count == 1
        assert mock_client.pages.update.call_count == 1


class TestNotionLoggerNotInstalled:
    """Tests quand notion-client n'est pas installe."""

    def test_init_raises_import_error(self):
        """Test que ImportError est levee si notion-client absent."""
        # Sauvegarder l'etat actuel
        import lyra.hestia.notion_logger as notion_module

        # Simuler l'absence de notion-client
        original_available = notion_module.NOTION_AVAILABLE
        notion_module.NOTION_AVAILABLE = False

        try:
            from lyra.hestia.notion_logger import NotionLogger

            with pytest.raises(ImportError, match="notion-client"):
                NotionLogger(token="token", database_id="db-id")
        finally:
            # Restaurer
            notion_module.NOTION_AVAILABLE = original_available


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
