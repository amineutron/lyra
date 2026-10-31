"""Les scripts qui ecrivent dans l'API tracking envoient son jeton local.

Regression : l'API exige `Authorization: Bearer <jeton>` sur toute ecriture
(fichier 0600 ecrit au demarrage). async_mcp_wrapper.py et smoke_mcps.py ne
l'envoyaient pas : chaque ecriture recevait un 401, avale par leur
try/except, et la progression n'apparaissait plus dans le tableau de bord.
"""
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _charger(nom):
    spec = importlib.util.spec_from_file_location(f"_essai_{nom}", SCRIPTS / f"{nom}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def jeton(tmp_path, monkeypatch):
    fichier = tmp_path / "token"
    fichier.write_text("jeton-essai\n")
    monkeypatch.setenv("TRACKING_TOKEN_FILE", str(fichier))
    return "jeton-essai"


def test_wrapper_envoie_le_jeton(jeton, monkeypatch):
    wrapper = _charger("async_mcp_wrapper")
    envoyees = []
    monkeypatch.setattr(wrapper.urllib.request, "urlopen",
                        lambda req, timeout=None: envoyees.append(req))

    wrapper._tracking_update("abc123", "http://127.0.0.1:8765", processed=3, log="x")

    assert len(envoyees) == 1
    req = envoyees[0]
    assert req.get_method() == "PUT"
    assert req.get_header("Authorization") == f"Bearer {jeton}"
    assert json.loads(req.data) == {"processed": 3, "log": "x"}


def test_smoke_envoie_le_jeton(jeton, monkeypatch):
    smoke = _charger("smoke_mcps")
    appels = []

    class Reponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"id": "s1"}

    def enregistrer(methode):
        def appel(url, **kwargs):
            appels.append((methode, url, kwargs.get("headers") or {}))
            return Reponse()
        return appel

    faux = types.SimpleNamespace(post=enregistrer("POST"), put=enregistrer("PUT"))
    monkeypatch.setitem(sys.modules, "requests", faux)

    smoke.report_tracking({"tv": {"ok": True, "tool_count": 5, "init_s": 0.2, "error": ""}})

    assert [m for m, _, _ in appels] == ["POST", "PUT"]
    for _, _, entetes in appels:
        assert entetes.get("Authorization") == f"Bearer {jeton}"


def test_sans_fichier_de_jeton_rien_ne_casse(tmp_path, monkeypatch):
    monkeypatch.setenv("TRACKING_TOKEN_FILE", str(tmp_path / "absent"))
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    wrapper = _charger("async_mcp_wrapper")
    # /run/tracking/token peut exister sur la machine : seul le type compte ici
    assert isinstance(wrapper.tracking_token(), str)
