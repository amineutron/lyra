# Lancer la suite de tests

```bash
make test                    # tout tests/ (utilise .venv si present, sinon python3)
make test PY=python3         # forcer l'interpreteur
python3 -m pytest tests/unit/rules -q   # ce que lance la CI GitHub
```

## Sans services externes

`make test` est vert sans Ollama, sans GPU ni service reseau : les modeles et
les MCP sont mockes. Deux dependances d'environnement sont geres explicitement :

- `config.yaml` (local, non versionne) : les tests d'integration RAG enhanced
  utilisent `config.yaml.example` copie en repertoire temporaire s'il manque
  (voir `tests/integration/rag_enhanced/conftest.py`). S'il existe, il est utilise tel quel.
- `chromadb` et `sentence_transformers` : necessaires a
  `tests/integration/rag_enhanced/test_pipeline_integration.py` (vrai RAG). Absents
  du python systeme, ces tests sont ignores avec une raison explicite.

## Suite complete (RAG reel)

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt chromadb sentence-transformers
make test
```

Le premier lancement telecharge le modele d'embeddings (all-MiniLM-L6-v2).
Les campagnes (`make campaign`) et smoke (`make smoke`) demandent en plus
Ollama et les serveurs MCP : ils ne font pas partie de `make test`.
