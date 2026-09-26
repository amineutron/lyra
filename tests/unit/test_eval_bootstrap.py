"""Chemin d'evaluation (roadmap #44) : config derivee de l'exemple, modeles, index."""
import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("eval_bootstrap", ROOT / "deploy" / "eval" / "bootstrap.py")
boot = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(boot)


@pytest.fixture(scope="module")
def example():
    return yaml.safe_load((ROOT / "config.yaml.example").read_text(encoding="utf-8"))


def test_config_texte_seul_et_un_mcp(example):
    cfg = boot.eval_config(example, {})
    assert list(cfg["mcp"]["servers"]) == ["denon"]
    assert cfg["mcp"]["servers"]["denon"]["env"] == {}
    assert all(m.get("tts_response") is False for m in cfg["modes"].values() if isinstance(m, dict))
    assert cfg["stt"]["device"] == "cpu"
    assert cfg["llm"]["model"] == cfg["models"]["ephaistos"]["name"]
    for section in ("n8n", "discord", "homeassistant", "notion"):
        assert cfg[section]["enabled"] is False
    assert cfg["tracking"]["api_url"] == "http://127.0.0.1:8765"


def test_modeles_legers_de_l_exemple(example):
    # decision 11 : les deux modeles legers, rien de plus gros
    assert boot.wanted_models(boot.eval_config(example, {})) == ["qwen2.5-coder:0.5b", "llama3.2:1b"]


def test_exemple_non_modifie(example):
    avant = yaml.safe_dump(example)
    boot.eval_config(example, {"DENON_HOST": "10.0.0.9"})
    assert yaml.safe_dump(example) == avant


def test_denon_reel_optionnel(example):
    cfg = boot.eval_config(example, {"DENON_HOST": "10.0.0.9", "HOME": "/x"})
    assert cfg["mcp"]["servers"]["denon"]["env"] == {"DENON_HOST": "10.0.0.9"}


@pytest.mark.parametrize("tags,attendu", [
    ({"models": []}, ["qwen2.5-coder:0.5b", "llama3.2:1b"]),
    ({"models": [{"name": "qwen2.5-coder:0.5b"}]}, ["llama3.2:1b"]),
    ({"models": [{"name": "qwen2.5-coder:0.5b"}, {"name": "llama3.2:1b"}]}, []),
])
def test_modeles_manquants(tags, attendu):
    assert boot.missing_models(tags, ["qwen2.5-coder:0.5b", "llama3.2:1b"]) == attendu


def test_nom_sans_etiquette_vaut_latest():
    assert boot.missing_models({"models": [{"name": "phi:latest"}]}, ["phi"]) == []


def test_index_vide(tmp_path):
    assert boot.index_is_empty(tmp_path)
    (tmp_path / "chroma.sqlite3").write_text("")
    assert not boot.index_is_empty(tmp_path)


def test_url_ollama(monkeypatch):
    assert boot.ollama_url({}) == "http://ollama:11434"
    assert boot.ollama_url({"OLLAMA_HOST": "gpu-box"}) == "http://gpu-box:11434"


def test_regression_aucune_adresse_fictive(example):
    # denon-mcp relit denon.host dans config.yaml : l'adresse d'exemple 203.0.113.X
    # donnait un timeout au lieu de « DENON_HOST not configured »
    cfg = boot.eval_config(example, {})
    assert cfg["denon"]["host"] == "" and cfg["tv"]["host"] == "" and cfg["hue"]["bridge_ip"] == ""
    assert "203.0.113" not in yaml.safe_dump(cfg["denon"]) + yaml.safe_dump(cfg["tv"]) + yaml.safe_dump(cfg["hue"])
    assert boot.eval_config(example, {"DENON_HOST": "10.0.0.9"})["denon"]["host"] == "10.0.0.9"
