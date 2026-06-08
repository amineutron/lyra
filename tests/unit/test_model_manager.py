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
        resp = ModelResponse(
            content="",
            model="LYRA",
            success=False,
            error="Timeout"
        )
        assert resp.content == ""
        assert resp.success is False
        assert resp.error == "Timeout"


# ---------------------------------------------------------------------------
# Fixture partagée : crée le ModelManager avec httpx.Client déjà mocké.
#
# Pourquoi fixture et non @patch par méthode ?
# ModelManager crée self._http = httpx.Client(...) dans __init__. Un décorateur
# @patch('httpx.Client') sur la méthode de test s'applique APRÈS la création du
# manager par le fixture 'manager', donc le vrai httpx.Client était appelé.
# En patchant ici, le mock est actif au moment de ModelManager.__init__.
# ---------------------------------------------------------------------------

@pytest.fixture
def config():
    """Config de test."""
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
def mock_http():
    """Mock du client httpx persistant. Retourne (mock_client, mock_class)."""
    mock_client = MagicMock()
    with patch("lyra.models.model_manager.httpx.Client", return_value=mock_client) as mock_cls:
        yield mock_client, mock_cls


@pytest.fixture
def manager(config, mock_http):
    """ModelManager avec client HTTP mocké."""
    mock_client, _ = mock_http
    m = ModelManager(config)
    # Garantit que self._http == mock_client
    assert m._http is mock_client
    return m, mock_client


class TestModelManager:
    """Tests pour ModelManager."""

    def test_initialization(self, manager):
        m, _ = manager
        assert m.ephaistos_model == "qwen2.5-coder:7b"
        assert m.lyra_model == "llama3.2:3b"
        assert m.ephaistos_temp == 0.1
        assert m.lyra_temp == 0.5

    def test_stats_initial(self, manager):
        m, _ = manager
        stats = m.get_stats()
        assert stats["ephaistos_calls"] == 0
        assert stats["lyra_calls"] == 0
        assert stats["total_calls"] == 0

    def test_call_ephaistos_success(self, manager):
        m, mock_client = manager

        mock_response = Mock()
        mock_response.json.return_value = {
            "message": {"content": '{"tool": "vm_start"}'}
        }
        mock_response.raise_for_status = Mock()
        mock_client.post.return_value = mock_response

        result = m.call_ephaistos("demarre preprod", "Tu es EPHAISTOS")

        assert result.success is True
        assert result.content == '{"tool": "vm_start"}'
        assert result.model == "EPHAISTOS"
        assert m._ephaistos_calls == 1

    def test_call_lyra_success(self, manager):
        m, mock_client = manager

        mock_response = Mock()
        mock_response.json.return_value = {
            "message": {"content": "Quelle VM tu veux demarrer?"}
        }
        mock_response.raise_for_status = Mock()
        mock_client.post.return_value = mock_response

        result = m.call_lyra("Pose une question", "Tu es LYRA")

        assert result.success is True
        assert "VM" in result.content
        assert result.model == "LYRA"
        assert m._lyra_calls == 1

    def test_call_timeout(self, manager):
        m, mock_client = manager
        mock_client.post.side_effect = httpx.TimeoutException("Timeout")

        result = m.call_ephaistos("test")

        assert result.success is False
        assert "Timeout" in result.error

    def test_call_http_error(self, manager):
        m, mock_client = manager

        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error",
            request=Mock(),
            response=mock_response
        )
        mock_client.post.return_value = mock_response

        result = m.call_ephaistos("test")

        assert result.success is False
        assert "HTTP error" in result.error

    def test_check_models_available(self, manager):
        m, mock_client = manager

        mock_response = Mock()
        mock_response.json.return_value = {
            "models": [
                {"name": "qwen2.5-coder:7b"},
                {"name": "llama3.2:3b"},
            ]
        }
        mock_response.raise_for_status = Mock()
        mock_client.get.return_value = mock_response

        available = m.check_models_available()

        assert available["ephaistos"] is True
        assert available["lyra"] is True

    def test_check_models_missing(self, manager):
        m, mock_client = manager

        mock_response = Mock()
        mock_response.json.return_value = {
            "models": [{"name": "mistral:7b"}]
        }
        mock_response.raise_for_status = Mock()
        mock_client.get.return_value = mock_response

        available = m.check_models_available()

        assert available["ephaistos"] is False
        assert available["lyra"] is False

    def test_call_with_system_prompt(self, manager):
        m, _ = manager
        with patch.object(m, '_call_model') as mock_call:
            mock_call.return_value = ModelResponse("", "EPHAISTOS", True)
            m.call_ephaistos("prompt", "system prompt")
            mock_call.assert_called_once()
            args, kwargs = mock_call.call_args
            assert kwargs.get('system_prompt') == "system prompt" or args[2] == "system prompt"

    def test_close(self, manager):
        m, mock_client = manager
        m.close()
        mock_client.close.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
