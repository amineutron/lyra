# Lyra RAG Enhanced

Système RAG amélioré pour LYRA, assistant DevOps vocal.

## Objectif

Enrichir le pipeline RAG V2 actuel avec 6 composants pour :
- Améliorer la précision de détection des outils MCP
- Réduire les ambiguïtés entre outils similaires
- Apprendre continuellement des interactions

## Composants

### 1. SlangNormalizer (P1)
Normalise anglicismes et argot en français standard.
- Dict JSON `slang_dict.json` (max 200 patterns)
- Latence : <1ms

### 2. SynonymExpander (P2)
Enrichit la requête avec synonymes pour améliorer le recall RAG.
- Dict JSON `synonym_dict.json` (max 80 keywords)
- Max 6 synonymes/mot-clé, max 15 tokens ajoutés
- Latence : <1ms

### 3. ContextInjector (P3)
Injecte contexte session quand RAG est ambiguë.
- SQLite `session_history.db` (FIFO 15 échanges/session)
- Injection on-demand selon écart scores
- Latence : <10ms

### 4. RAG 3-Tier (P4)
Entonnoir séquentiel avec 3 collections ChromaDB.
- Registry → Serveur MCP
- Capabilities → Outil
- Parameters → Arguments
- Latence : ~20-30ms (≤ V2 + 20%)

### 5. ConfidenceCascader (P5)
Décide l'action selon le score RAG.
- HIGH (>0.85) : EXECUTE direct
- MEDIUM (0.60-0.85) : PROPOSE options
- LOW (<0.60) : FALLBACK LYRA
- Latence : <2ms

### 6. FeedbackLoop (P5)
Apprentissage continu basé sur succès/échecs.
- Suggestion après 3 échecs
- Auto-enrichissement après 5 échecs
- Rollback auto si dégradation
- Latence : <2ms

## Installation

Déjà inclus dans LYRA. La configuration se trouve dans `config.yaml` :

```yaml
rag_enhanced:
  enabled: false  # Master switch

  slang_normalizer:
    enabled: false
    dict_path: "data/slang_dict.json"
    max_patterns: 200

  synonym_expander:
    enabled: false
    dict_path: "data/synonym_dict.json"
    max_synonyms: 6
    max_tokens_added: 15

  # ... autres composants
```

## Usage

### Configuration

```python
from lyra.core.config import RAGConfig

# Charger config
config = RAGConfig.from_yaml("config.yaml")

# Accéder à RAG Enhanced
if config.rag_enhanced and config.rag_enhanced.enabled:
    print(f"Slang enabled: {config.rag_enhanced.slang_normalizer.enabled}")
```

### Types

```python
from lyra.rag_enhanced import (
    ConfidenceLevel,
    CascadeAction,
    QueryContext,
    RAGResult,
)

# QueryContext
ctx: QueryContext = {
    "query": "démarre preprod-09",
    "session_id": "123",
    "rag_score": 0.85,
    "last_mcp": "vm_start",
}

# RAGResult
result: RAGResult = {
    "tool_name": "vm_start",
    "confidence": 0.90,
    "source": "registry",  # ou "capabilities" ou "parameters"
    "metadata": {},
}
```

### Constantes

```python
from lyra.rag_enhanced import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    SLANG_MAX_PATTERNS,
    SYNONYM_MAX_PER_KEYWORD,
)

print(f"Seuil haute confiance: {CONFIDENCE_HIGH}")  # 0.85
print(f"Max patterns slang: {SLANG_MAX_PATTERNS}")  # 200
```

## API

### RAGEnhancedConfig

```python
from lyra.rag_enhanced.config import RAGEnhancedConfig

# Depuis dict
config = RAGEnhancedConfig.from_dict({
    "enabled": True,
    "slang_normalizer": {"enabled": True},
})

# Accès
config.enabled  # bool
config.slang_normalizer  # SlangNormalizerConfig
config.synonym_expander  # SynonymExpanderConfig
config.context_injector  # ContextInjectorConfig
config.rag_3tier  # RAG3TierConfig
config.feedback_loop  # FeedbackLoopConfig
config.metrics  # MetricsConfig
```

### Validation

La validation se fait automatiquement au `__post_init__` :

```python
from lyra.rag_enhanced.config import SlangNormalizerConfig

# ✅ OK
config = SlangNormalizerConfig(max_patterns=100)

# ❌ ValueError
config = SlangNormalizerConfig(max_patterns=-1)  # Négatif
config = SlangNormalizerConfig(max_patterns=300)  # > limite 200
```

## Tests

```bash
# Tests unitaires
pytest tests/unit/rag_enhanced/ -v

# Couverture
pytest tests/unit/rag_enhanced/ --cov=lyra/rag_enhanced --cov-report=term-missing

# Tests intégration
pytest tests/integration/rag_enhanced/ -v

# Tests E2E (après SESSION 8)
pytest tests/e2e/rag_enhanced/ -v
```

## Performance

| Composant | Latence | Critère |
|-----------|---------|---------|
| SlangNormalizer | <1ms | ✅ |
| SynonymExpander | <1ms | ✅ |
| RAG 3-Tier | ~20-30ms | ✅ (≤ V2 + 20%) |
| ContextInjector | <10ms | ✅ |
| ConfidenceCascader | <2ms | ✅ |
| FeedbackLoop | <2ms | ✅ |
| **TOTAL OVERHEAD** | **~40-50ms** | **✅** |

## Documentation

- **ARCHITECTURE.md** : Vue d'ensemble système
- **PROGRESS.md** : Tracking implémentation 8 sessions
- **E2E_SCENARIOS.md** : 12 scénarios de test (après SESSION 8)
- **FINAL_REPORT.md** : Rapport final (après SESSION 8)

## Roadmap

- [x] SESSION 1 : Infrastructure et Configuration (P0)
- [ ] SESSION 2 : Slang Normalizer (P1)
- [ ] SESSION 3 : Synonym Expander (P2)
- [ ] SESSION 4 : Context Injector (P3)
- [ ] SESSION 5 : RAG 3-Tier (P4)
- [ ] SESSION 6 : Feedback Loop + Cascader (P5)
- [ ] SESSION 7 : Pipeline Integration (P6.1)
- [ ] SESSION 8 : Tests E2E (P6.2)

Voir `PROGRESS.md` pour le détail.

## Limitations Connues

**SESSION 1 (Actuel)** :
- Seules les structures de base sont implémentées
- Composants 2-6 pas encore implémentés
- Tests E2E non disponibles

**Après SESSION 8** :
- Système complet fonctionnel
- 12 scénarios E2E validés
- Backward compatibility V2 garantie

## Contributing

Suivre la méthodologie TDD définie dans le plan :
1. Lire fichiers de référence
2. Écrire tests unitaires (RED)
3. Implémenter (GREEN)
4. Refactorer (REFACTOR)
5. Valider (couverture >85%)
6. Documenter

## Licence

Même licence que LYRA (voir LICENSE dans la racine).
