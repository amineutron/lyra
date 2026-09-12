# Setup Développement - RAG Enhanced

Guide pour configurer l'environnement de développement RAG Enhanced.

## Installation Rapide

### 1. Dépendances Runtime (Production)

```bash
pip install -r requirements.txt
```

### 2. Dépendances Dev (Tests, Linters)

```bash
pip install -r requirements-dev.txt
```

**Contenu** :
- `pytest>=7.0.0` - Framework de tests
- `pytest-cov>=4.0.0` - Couverture de code
- `pytest-benchmark>=4.0.0` - **Benchmarks performance** (critique pour S2-S8)
- `pytest-asyncio>=0.21.0` - Tests async
- `ruff>=0.1.0` - Linter rapide
- `mypy>=1.0.0` - Type checking
- `coverage>=7.0.0` - Rapports couverture
- `ipython>=8.0.0` - REPL amélioré
- `ipdb>=0.13.0` - Debugger

## Vérification Installation

```bash
# Vérifier pytest-benchmark
python -c "import pytest_benchmark; print('✅ pytest-benchmark OK')"

# Vérifier pytest
pytest --version

# Vérifier ruff
ruff --version

# Vérifier mypy
mypy --version
```

## Lancer les Tests

### Tests SESSION 2 (Slang Normalizer)

```bash
# Tous les tests
pytest tests/unit/rag_enhanced/test_slang_normalizer.py -v

# Avec couverture
pytest tests/unit/rag_enhanced/test_slang_normalizer.py --cov=lyra/rag_enhanced/slang_normalizer --cov-report=term-missing

# Benchmarks performance (nécessite pytest-benchmark)
pytest tests/unit/rag_enhanced/test_slang_normalizer.py::TestSlangNormalizer::test_normalize_performance -v
```

### Tests Complets RAG Enhanced

```bash
# Tous les tests unitaires
pytest tests/unit/rag_enhanced/ -v

# Avec couverture globale
pytest tests/unit/rag_enhanced/ --cov=lyra/rag_enhanced --cov-report=html
# → Ouvre htmlcov/index.html dans un navigateur

# Intégration
pytest tests/integration/rag_enhanced/ -v

# E2E (après SESSION 8)
pytest tests/e2e/rag_enhanced/ -v
```

## Linter et Type Checking

### Ruff (Linter)

```bash
# Vérifier tout le code
ruff check lyra/rag_enhanced/

# Auto-fix
ruff check lyra/rag_enhanced/ --fix

# Formater
ruff format lyra/rag_enhanced/
```

### MyPy (Type Checking)

```bash
# Vérifier types
mypy lyra/rag_enhanced/

# Avec rapport détaillé
mypy lyra/rag_enhanced/ --show-error-codes
```

## Scripts de Validation

### SESSION 2

```bash
./docs/rag_enhanced/validate_session2.sh
```

### Toutes les Sessions

```bash
# À venir après SESSION 8
./docs/rag_enhanced/validate_all_sessions.sh
```

## Structure Projet

```
lyra/
├── requirements.txt           # Dépendances runtime
├── requirements-dev.txt       # Dépendances dev (nouveau)
├── lyra/
│   └── rag_enhanced/
│       ├── __init__.py
│       ├── slang_normalizer.py
│       ├── synonym_expander.py  (SESSION 3)
│       └── ...
├── tests/
│   ├── unit/rag_enhanced/
│   ├── integration/rag_enhanced/
│   └── e2e/rag_enhanced/
└── docs/rag_enhanced/
    ├── DEV_SETUP.md           # Ce fichier
    ├── TODO_SESSION7.md       # Checklist SESSION 7
    └── ...
```

## Dépendances Optionnelles

### pytest-benchmark

**Requis pour** : Tests performance dans SESSION 2, 3, 5, 7, 8

**Alternative** : Tests manuels existent (`test_*_performance_manual`)

**Installation seule** :
```bash
pip install pytest-benchmark
```

### CUDA (si GPU disponible)

Pour faster-whisper avec GPU :
```bash
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
```

## Troubleshooting

### pytest-benchmark ne s'installe pas

**Symptôme** : Erreur lors de `pip install pytest-benchmark`

**Solution** :
1. Les tests manuels alternatifs existent déjà
2. Ou installer avec `--no-deps` :
   ```bash
   pip install pytest-benchmark --no-deps
   ```

### Conflit de versions

**Solution** : Créer un venv propre
```bash
python -m venv .venv-dev
source .venv-dev/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### Tests lents

**Solution** : Utiliser pytest-xdist pour parallélisation
```bash
pip install pytest-xdist
pytest tests/unit/rag_enhanced/ -v -n auto
```

## CI/CD

Pour intégrer dans CI/CD (GitHub Actions, GitLab CI, etc.) :

```yaml
# .github/workflows/test.yml
steps:
  - name: Install dependencies
    run: |
      pip install -r requirements.txt
      pip install -r requirements-dev.txt

  - name: Run tests
    run: |
      pytest tests/unit/rag_enhanced/ -v --cov=lyra/rag_enhanced

  - name: Type check
    run: |
      mypy lyra/rag_enhanced/

  - name: Lint
    run: |
      ruff check lyra/rag_enhanced/
```

---

**Dernière mise à jour** : 2026-02-13
**Maintenu par** : Claude Code
**Questions** : Voir ARCHITECTURE.md, PROGRESS.md
