"""Regression 2026-10-31 : l'API tracking exige un jeton Bearer sur les ecritures
(mcp-tracking >= 0.2.0). `_tracking_update` du wrapper n'en envoyait pas : les
mises a jour de progression recevaient un 401 avalé en silence.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import async_mcp_wrapper


@pytest.fixture
def captured(monkeypatch, tmp_path):
    """Capture la requete envoyee par _tracking_update, jeton fourni par fichier."""
    token_file = tmp_path / "token"
    token_file.write_text("jeton-de-test\n")
    monkeypatch.setenv("TRACKING_TOKEN_FILE", str(token_file))

    requests = []

    def fake_urlopen(req, timeout=None):
        requests.append(req)

    monkeypatch.setattr(async_mcp_wrapper.urllib.request, "urlopen", fake_urlopen)
    return requests


def test_la_mise_a_jour_envoie_le_jeton_bearer(captured):
    async_mcp_wrapper._tracking_update("abcd1234", "http://127.0.0.1:8765", processed=42)

    assert len(captured) == 1
    req = captured[0]
    assert req.get_method() == "PUT"
    assert req.get_header("Authorization") == "Bearer jeton-de-test"
    assert req.get_header("Content-type") == "application/json"


@pytest.mark.parametrize("tracking_id, api, kwargs", [
    ("", "http://127.0.0.1:8765", {"processed": 1}),   # pas de session
    ("abcd1234", "", {"processed": 1}),                # pas d'API configuree
    ("abcd1234", "http://127.0.0.1:8765", {}),         # rien a envoyer
])
def test_aucun_appel_sans_session_api_ou_donnee(captured, tracking_id, api, kwargs):
    async_mcp_wrapper._tracking_update(tracking_id, api, **kwargs)
    assert captured == []
