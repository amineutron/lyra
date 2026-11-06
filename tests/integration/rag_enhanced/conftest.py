"""Fixtures d'integration RAG enhanced : config.yaml de repli.

config.yaml est local (non versionne). Sur un clone neuf, ou dans un worktree,
il n'existe pas : on utilise alors config.yaml.example dans un repertoire
temporaire, sans toucher a l'arbre de travail. Si config.yaml existe, il est
utilise tel quel (comportement de prod).
"""

import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def config_yaml_de_repli(tmp_path, monkeypatch):
    if (ROOT / "config.yaml").exists():
        return
    example = ROOT / "config.yaml.example"
    if not example.exists():
        pytest.skip("ni config.yaml ni config.yaml.example disponibles")
    shutil.copy(example, tmp_path / "config.yaml")
    monkeypatch.chdir(tmp_path)
    from tests.integration.rag_enhanced import test_pipeline_integration as mod
    monkeypatch.setattr(mod, "CONFIG_PATH", tmp_path / "config.yaml")
