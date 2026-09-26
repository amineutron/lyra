"""OLLAMA_HOST prime sur config.yaml pour l'URL Ollama (roadmap #44)."""
import pytest

from lyra.core.config import RAGConfig, ollama_url_depuis_env


@pytest.mark.parametrize("valeur, attendu", [
    (None, None), ("", None), ("   ", None),
    ("gpu-box", "http://gpu-box:11434"),
    ("gpu-box:11435", "http://gpu-box:11435"),
    ("http://10.0.0.5:11434/", "http://10.0.0.5:11434"),
    ("https://ollama.example.org", "https://ollama.example.org"),
])
def test_normalisation(valeur, attendu):
    assert ollama_url_depuis_env(valeur) == attendu


def test_env_prime_sur_config(monkeypatch):
    config = RAGConfig()
    config.llm = {"base_url": "http://fichier:11434"}
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    assert config.get_ollama_base_url() == "http://fichier:11434"
    monkeypatch.setenv("OLLAMA_HOST", "distant:11434")
    assert config.get_ollama_base_url() == "http://distant:11434"


def test_defaut_sans_env_ni_config(monkeypatch):
    # priorite : OLLAMA_HOST > config.yaml (llm.base_url) > defaut local
    monkeypatch.delenv("OLLAMA_HOST", raising=False)
    config = RAGConfig()
    config.llm = {}
    assert config.get_ollama_base_url() == "http://localhost:11434"
    monkeypatch.setenv("OLLAMA_HOST", "   ")
    assert config.get_ollama_base_url() == "http://localhost:11434"
