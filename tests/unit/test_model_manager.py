"""
Tests unitaires pour ModelManager.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import httpx

from lyra.models.model_manager import ModelManager, ModelResponse
from lyra.core.config import RAGConfig, ModelsConfig, ModelConfig


class TestModelResponse:
    """Tests pour ModelResponse."""

    def test_successful_response(self):
        """Test d'une reponse reussie."""
        resp = ModelResponse(
            content="Hello",
            model="EPHAISTOS",
            success=True,
            error=None
        )
        assert resp.content == "Hello"
        assert resp.model == "EPHAISTOS"
        assert resp.success is True
        assert resp.error is None

    def test_failed_response(self):
        """Test d'une reponse echouee."""
        resp = ModelResponse(
            content="",
            model="LYRA",
            success=False,
            error="Timeout"
        )
        assert resp.content == ""
        assert resp.success is False
        assert resp.error == "Timeout"


class TestModelManager:
    """Tests pour ModelManager."""

    @pytest.fixture
    def config(self):
        """Cree une config de test."""
        return RAGConfig.from_dict({
            "llm": {
                "base_url": "http://localhost:11434",
                "timeout": 60
            },
            "models": {
                "ephaistos": {"name": "qwen2.5-coder:7b", "temperature": 0.1},
                "lyra": {"name": "llama3.2:3b", "temperature": 0.5}
            }
        })

    @pytest.fixture
    def manager(self, config):
        """Cree un ModelManager de test."""
        return ModelManager(config)

    def test_initialization(self, manager, config):
        """Test d'initialisation."""
        assert manager.ephaistos_model == "qwen2.5-coder:7b"
        assert manager.lyra_model == "llama3.2:3b"
        assert manager.ephaistos_temp == 0.1
        assert manager.lyra_temp == 0.5

    def test_stats_initial(self, manager):
        """Test des stats initiales."""
        stats = manager.get_stats()
        assert stats["ephaistos_calls"] == 0
        assert stats["lyra_calls"] == 0
        assert stats["total_calls"] == 0

    @patch('httpx.Client')
    def test_call_ephaistos_success(self, mock_client_class, manager):
        """Test d'un appel EPHAISTOS reussi."""
        # Setup mock
        mock_response = Mock()
        mock_response.json.return_value = {
            "message": {"content": '{"tool": "vm_start"}'}
        }
        mock_response.raise_for_status = Mock()

        mock_client = MagicMock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=None)
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        # Call
        result = manager.call_ephaistos("demarre preprod", "Tu es EPHAISTOS")

        # Verify
        assert result.success is True
        assert result.content == '{"tool": "vm_start"}'
        assert result.model == "EPHAISTOS"

        # Verify stats updated
        assert manager._ephaistos_calls == 1

    @patch('httpx.Client')
    def test_call_lyra_success(self, mock_client_class, manager):
        """Test d'un appel LYRA reussi."""
        # Setup mock
        mock_response = Mock()
        mock_response.json.return_value = {
            "message": {"content": "Quelle VM tu veux demarrer?"}
        }
        mock_response.raise_for_status = Mock()

        mock_client = MagicMock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=None)
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        # Call
        result = manager.call_lyra("Pose une question", "Tu es LYRA")

        # Verify
        assert result.success is True
        assert "VM" in result.content
        assert result.model == "LYRA"

        # Verify stats updated
        assert manager._lyra_calls == 1

    @patch('httpx.Client')
    def test_call_timeout(self, mock_client_class, manager):
        """Test d'un timeout."""
        mock_client = MagicMock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=None)
        mock_client.post.side_effect = httpx.TimeoutException("Timeout")
        mock_client_class.return_value = mock_client

        result = manager.call_ephaistos("test")

        assert result.success is False
        assert "Timeout" in result.error

    @patch('httpx.Client')
    def test_call_http_error(self, mock_client_class, manager):
        """Test d'une erreur HTTP."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error",
            request=Mock(),
            response=mock_response
        )

        mock_client = MagicMock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=None)
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        result = manager.call_ephaistos("test")

        assert result.success is False
        assert "HTTP error" in result.error

    @patch('httpx.Client')
    def test_check_models_available(self, mock_client_class, manager):
        """Test de verification des modeles disponibles."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "models": [
                {"name": "qwen2.5-coder:7b"},
                {"name": "llama3.2:3b"},
            ]
        }
        mock_response.raise_for_status = Mock()

        mock_client = MagicMock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=None)
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        available = manager.check_models_available()

        assert available["ephaistos"] is True
        assert available["lyra"] is True

    @patch('httpx.Client')
    def test_check_models_missing(self, mock_client_class, manager):
        """Test de modeles manquants."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "models": [
                {"name": "mistral:7b"},
            ]
        }
        mock_response.raise_for_status = Mock()

        mock_client = MagicMock()
        mock_client.__enter__ = Mock(return_value=mock_client)
        mock_client.__exit__ = Mock(return_value=None)
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        available = manager.check_models_available()

        assert available["ephaistos"] is False
        assert available["lyra"] is False

    def test_call_with_system_prompt(self, manager):
        """Test que le system prompt est inclus."""
        with patch.object(manager, '_call_model') as mock_call:
            mock_call.return_value = ModelResponse("", "EPHAISTOS", True)

            manager.call_ephaistos("prompt", "system prompt")

            mock_call.assert_called_once()
            args, kwargs = mock_call.call_args
            assert kwargs.get('system_prompt') == "system prompt" or args[2] == "system prompt"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
