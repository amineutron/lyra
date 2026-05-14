"""
Tests unitaires pour HestiaExecutor.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from lyra.hestia.executor import (
    HestiaExecutor,
    ExecutionContext,
    ExecutionResult
)
from modules.mcp import MCPResult


class TestExecutionContext:
    """Tests pour ExecutionContext."""

    def test_basic_context(self):
        """Test de creation d'un contexte simple."""
        ctx = ExecutionContext(
            user_query="demarre preprod-09",
            tool_name="vm_start",
            arguments={"vm_name": "preprod-09"}
        )
        assert ctx.user_query == "demarre preprod-09"
        assert ctx.tool_name == "vm_start"
        assert ctx.arguments == {"vm_name": "preprod-09"}
        assert ctx.session_id is None
        assert ctx.request_id is None
        assert isinstance(ctx.timestamp, datetime)

    def test_context_with_session(self):
        """Test de contexte avec session."""
        ctx = ExecutionContext(
            user_query="test",
            tool_name="vm_status",
            arguments={},
            session_id="sess-123",
            request_id="req-456"
        )
        assert ctx.session_id == "sess-123"
        assert ctx.request_id == "req-456"

    def test_context_timestamp_default(self):
        """Test que le timestamp est auto-genere."""
        before = datetime.now()
        ctx = ExecutionContext(
            user_query="test",
            tool_name="test",
            arguments={}
        )
        after = datetime.now()

        assert before <= ctx.timestamp <= after


class TestExecutionResult:
    """Tests pour ExecutionResult."""

    def test_successful_result(self):
        """Test d'un resultat reussi."""
        result = ExecutionResult(
            success=True,
            content="VM preprod-09 demarree",
            duration_ms=1234.5
        )
        assert result.success is True
        assert result.content == "VM preprod-09 demarree"
        assert result.error is None
        assert result.duration_ms == 1234.5
        assert result.logged_to_notion is False

    def test_failed_result(self):
        """Test d'un resultat echoue."""
        result = ExecutionResult(
            success=False,
            content="",
            error="VM not found",
            duration_ms=50.0
        )
        assert result.success is False
        assert result.content == ""
        assert result.error == "VM not found"

    def test_result_with_notion_logging(self):
        """Test d'un resultat logge vers Notion."""
        result = ExecutionResult(
            success=True,
            content="OK",
            logged_to_notion=True
        )
        assert result.logged_to_notion is True


class TestHestiaExecutor:
    """Tests pour HestiaExecutor."""

    @pytest.fixture
    def config(self):
        """Configuration de test."""
        return {
            "mcp": {
                "servers": {
                    "fedora": {
                        "enabled": True,
                        "command": "node",
                        "args": ["/path/to/server.js"],
                        "timeout": 60
                    }
                }
            }
        }

    @pytest.fixture
    def mock_mcp_manager(self):
        """Mock du MCPManager."""
        with patch('lyra.hestia.executor.MCPManager') as mock:
            manager = Mock()
            mock.return_value = manager
            yield manager

    @pytest.fixture
    def executor(self, config, mock_mcp_manager):
        """Cree un executor avec MCPManager mocke."""
        return HestiaExecutor(config)

    def test_initialization(self, executor, mock_mcp_manager):
        """Test d'initialisation."""
        assert executor.mcp_manager is mock_mcp_manager
        assert executor.metrics is not None
        assert executor.notion is None

    def test_initialization_with_notion_disabled(self, config):
        """Test d'initialisation avec Notion desactive."""
        with patch('lyra.hestia.executor.MCPManager'):
            executor = HestiaExecutor(config, notion_enabled=False)
            assert executor.notion is None

    @patch('lyra.hestia.executor.MCPManager')
    @patch('lyra.hestia.executor.NotionLogger')
    def test_initialization_with_notion_enabled(self, mock_notion, mock_mcp, config):
        """Test d'initialisation avec Notion active."""
        notion_config = {
            "token": "secret-token",
            "database_id": "db-id-123"
        }

        executor = HestiaExecutor(
            config,
            notion_enabled=True,
            notion_config=notion_config
        )

        mock_notion.assert_called_once_with(
            token="secret-token",
            database_id="db-id-123"
        )

    @patch('lyra.hestia.executor.MCPManager')
    def test_initialization_notion_import_error(self, mock_mcp, config):
        """Test quand Notion n'est pas installe."""
        with patch('lyra.hestia.executor.NotionLogger', side_effect=ImportError("notion-client not installed")):
            executor = HestiaExecutor(
                config,
                notion_enabled=True,
                notion_config={"token": "x", "database_id": "y"}
            )
            assert executor.notion is None

    def test_execute_success(self, executor, mock_mcp_manager):
        """Test d'execution reussie."""
        mock_mcp_manager.call_tool.return_value = MCPResult(
            success=True,
            content="VM preprod-09 started successfully"
        )

        result = executor.execute("vm_start", {"vm_name": "preprod-09"})

        assert result.success is True
        assert "preprod-09" in result.content
        assert result.error is None
        assert result.duration_ms > 0
        mock_mcp_manager.call_tool.assert_called_once_with(
            "vm_start",
            {"vm_name": "preprod-09"}
        )

    def test_execute_failure(self, executor, mock_mcp_manager):
        """Test d'execution echouee."""
        mock_mcp_manager.call_tool.return_value = MCPResult(
            success=False,
            content="",
            error="VM not found: sandbox-99"
        )

        result = executor.execute("vm_start", {"vm_name": "sandbox-99"})

        assert result.success is False
        assert result.error == "VM not found: sandbox-99"

    def test_execute_exception(self, executor, mock_mcp_manager):
        """Test quand MCPManager leve une exception."""
        mock_mcp_manager.call_tool.side_effect = Exception("Connection timeout")

        result = executor.execute("vm_start", {"vm_name": "test"})

        assert result.success is False
        assert "Connection timeout" in result.error

    def test_execute_with_context(self, executor, mock_mcp_manager):
        """Test d'execution avec contexte."""
        mock_mcp_manager.call_tool.return_value = MCPResult(
            success=True,
            content="OK"
        )

        context = ExecutionContext(
            user_query="demarre preprod",
            tool_name="vm_start",
            arguments={"vm_name": "preprod-09"},
            session_id="test-session"
        )

        result = executor.execute(
            "vm_start",
            {"vm_name": "preprod-09"},
            context=context
        )

        assert result.success is True

    def test_execute_records_metrics(self, executor, mock_mcp_manager):
        """Test que l'execution enregistre les metriques."""
        mock_mcp_manager.call_tool.return_value = MCPResult(
            success=True,
            content="OK"
        )

        # Execute plusieurs fois
        executor.execute("vm_start", {"vm_name": "vm1"})
        executor.execute("vm_start", {"vm_name": "vm2"})
        executor.execute("vm_stop", {"vm_name": "vm1"})

        # Verifier les metriques
        metrics = executor.get_metrics()
        assert metrics["total_executions"] == 3
        assert metrics["total_success"] == 3

    def test_get_available_tools(self, executor, mock_mcp_manager):
        """Test de recuperation des outils disponibles."""
        mock_mcp_manager.get_all_tools.return_value = [
            {"name": "vm_start", "description": "Start VM"},
            {"name": "vm_stop", "description": "Stop VM"},
        ]

        tools = executor.get_available_tools()

        assert len(tools) == 2
        assert tools[0]["name"] == "vm_start"
        mock_mcp_manager.get_all_tools.assert_called_once()

    def test_get_servers(self, executor, mock_mcp_manager):
        """Test de recuperation des serveurs."""
        mock_mcp_manager.get_server_names.return_value = ["fedora", "tv", "hue"]

        servers = executor.get_servers()

        assert servers == ["fedora", "tv", "hue"]

    def test_is_dangerous_tool_true(self, executor):
        """Test de detection d'outils dangereux."""
        assert executor.is_dangerous_tool("vm_destroy") is True
        assert executor.is_dangerous_tool("backup_restore") is True
        assert executor.is_dangerous_tool("backup_clean") is True
        assert executor.is_dangerous_tool("vm_delete") is True

    def test_is_dangerous_tool_false(self, executor):
        """Test que les outils normaux ne sont pas dangereux."""
        assert executor.is_dangerous_tool("vm_start") is False
        assert executor.is_dangerous_tool("vm_status") is False
        assert executor.is_dangerous_tool("backup_list") is False
        assert executor.is_dangerous_tool("tv.power_on") is False

    def test_is_dangerous_tool_with_prefix(self, executor):
        """Test avec prefixe de serveur."""
        assert executor.is_dangerous_tool("fedora.vm_destroy") is True
        assert executor.is_dangerous_tool("fedora.backup_clean") is True
        assert executor.is_dangerous_tool("fedora.vm_start") is False

    def test_close(self, executor, mock_mcp_manager):
        """Test de fermeture."""
        executor.close()
        mock_mcp_manager.close.assert_called_once()


class TestHestiaExecutorWithNotion:
    """Tests pour HestiaExecutor avec Notion active."""

    @pytest.fixture
    def config(self):
        return {
            "mcp": {
                "servers": {}
            }
        }

    @pytest.fixture
    def notion_config(self):
        return {
            "token": "test-token",
            "database_id": "test-db-id"
        }

    @patch('lyra.hestia.executor.MCPManager')
    @patch('lyra.hestia.executor.NotionLogger')
    def test_execute_logs_to_notion(self, mock_notion_class, mock_mcp_class, config, notion_config):
        """Test que l'execution logge vers Notion."""
        mock_mcp = Mock()
        mock_mcp.call_tool.return_value = MCPResult(success=True, content="OK")
        mock_mcp_class.return_value = mock_mcp

        mock_notion = Mock()
        mock_notion.log_start.return_value = True
        mock_notion.log_end.return_value = True
        mock_notion_class.return_value = mock_notion

        executor = HestiaExecutor(
            config,
            notion_enabled=True,
            notion_config=notion_config
        )

        context = ExecutionContext(
            user_query="test",
            tool_name="vm_start",
            arguments={"vm_name": "test"}
        )

        result = executor.execute("vm_start", {"vm_name": "test"}, context=context)

        # Verifier les appels Notion
        mock_notion.log_start.assert_called_once_with(context)
        mock_notion.log_end.assert_called_once()
        assert result.logged_to_notion is True

    @patch('lyra.hestia.executor.MCPManager')
    @patch('lyra.hestia.executor.NotionLogger')
    def test_execute_without_context_skips_notion(self, mock_notion_class, mock_mcp_class, config, notion_config):
        """Test que sans contexte, Notion n'est pas appele."""
        mock_mcp = Mock()
        mock_mcp.call_tool.return_value = MCPResult(success=True, content="OK")
        mock_mcp_class.return_value = mock_mcp

        mock_notion = Mock()
        mock_notion_class.return_value = mock_notion

        executor = HestiaExecutor(
            config,
            notion_enabled=True,
            notion_config=notion_config
        )

        result = executor.execute("vm_start", {"vm_name": "test"})

        # Notion ne devrait pas etre appele sans contexte
        mock_notion.log_start.assert_not_called()
        mock_notion.log_end.assert_not_called()
        assert result.logged_to_notion is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
