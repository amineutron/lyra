# Pipeline Enhanced - Flow Complet

**SESSION 7 (P6.1)** - Documentation du workflow intégré

---

## Vue d'Ensemble

Le **EnhancedPipeline** enrichit le pipeline RAG V2 avec 6 composants pour améliorer la précision et l'apprentissage continu.

**Overhead cible** : <50ms vs V2 (hors LLM/MCP)

---

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│                     USER QUERY                              │
└──────────────────┬─────────────────────────────────────────┘
                   │
                   ▼
         ┌─────────────────────┐
         │  EnhancedPipeline   │
         │  (enabled=true?)    │
         └─────────┬───────────┘
                   │
         ┌─────────┴─────────┐
         │                   │
         ▼                   ▼
    [ENHANCED]          [V2 FALLBACK]
         │                   │
         │                   └────► Pipeline V2 ────► RESULT
         │
         ▼
┌──────────────────────────────────────────────────────────────┐
│  ÉTAPE 1 : Slang Normalizer         <1ms                     │
│  "start vm" → "démarre vm"                                   │
└──────────────────┬───────────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────────┐
│  ÉTAPE 2 : Synonym Expander         <1ms                     │
│  "démarre vm" → "démarre machine virtuelle serveur instance" │
└──────────────────┬───────────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────────┐
│  ÉTAPE 3 : RAG (3-Tier OU V2)      20-30ms                  │
│  RAG3Tier.cascade_search() → rag_results                    │
│  OU SemanticRetriever (V2 fallback)                         │
└──────────────────┬───────────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────────┐
│  ÉTAPE 4 : Confidence Cascader      <2ms                     │
│  rag_score → CascadeAction                                   │
│                                                               │
│  HIGH (>0.85)    → EXECUTE direct                            │
│  MEDIUM (0.60-0.85) → PROPOSE options                        │
│  LOW (<0.60)     → FALLBACK LYRA                             │
└──────────────────┬───────────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────────┐
│  ÉTAPE 5 : Context Injector (si MEDIUM + gap <0.10)  ~10ms  │
│  Inject derniers N échanges session                         │
│  "[ctx: last_mcp=vm_start, frequent_mcp=vm_clone, ...]"     │
└──────────────────┬───────────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────────┐
│  ÉTAPE 6 : Pipeline V2              ~100-500ms (LLM+MCP)    │
│  EPHAISTOS → LYRA → HESTIA → result                         │
└──────────────────┬───────────────────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────────┐
│  ÉTAPE 7 : Feedback Loop            <2ms                     │
│  record_interaction(query, tool, score, success)            │
└──────────────────┬───────────────────────────────────────────┘
                   │
                   ▼
              ┌─────────┐
              │  RESULT │
              └─────────┘
```

---

## Workflow Détaillé

### Scénario Exemple : "start preprod-09"

```
USER INPUT: "start preprod-09"
    │
    ▼
[ÉTAPE 1] Slang Normalizer (0.8ms)
    Input:  "start preprod-09"
    Output: "démarre preprod-09"
    │
    ▼
[ÉTAPE 2] Synonym Expander (1.2ms)
    Input:  "démarre preprod-09"
    Output: "démarre lance boot machine vm preprod-09"
    │
    ▼
[ÉTAPE 3] RAG 3-Tier (25.4ms)
    Search: "démarre lance boot machine vm preprod-09"
    Results: [
        {'tool_name': 'vm_start', 'score': 0.92, 'source': 'capabilities'},
        {'tool_name': 'vm_clone', 'score': 0.65, 'source': 'capabilities'},
        ...
    ]
    │
    ▼
[ÉTAPE 4] Confidence Cascader (0.5ms)
    rag_score: 0.92
    gap: 0.27 (>0.10, pas besoin contexte)
    Decision: HIGH → EXECUTE
    │
    ▼
[ÉTAPE 5] Context Injector (SKIP - HIGH confidence)
    │
    ▼
[ÉTAPE 6] Pipeline V2 (120ms LLM + 80ms MCP)
    EPHAISTOS analyze: {"name": "vm_start", "arguments": {"vm_name": "preprod-09"}}
    LYRA confirm: "Je démarre la VM preprod-09 ?"
    [USER] "Oui"
    HESTIA execute: vm_start(preprod-09) → SUCCESS
    LYRA format: "La VM preprod-09 est démarrée (IP: 192.168.122.146)"
    │
    ▼
[ÉTAPE 7] Feedback Loop (1.5ms)
    record_interaction(
        query="start preprod-09",
        tool_name="vm_start",
        rag_score=0.92,
        success=True
    )
    │
    ▼
RESULT:
    response: "La VM preprod-09 est démarrée (IP: 192.168.122.146)"
    normalized_query: "démarre preprod-09"
    expanded_query: "démarre lance boot machine vm preprod-09"
    rag_source: "capabilities"
    cascade_action: "execute"
    rag_score: 0.92
    feedback_recorded: True
    metrics: {
        'slang_latency_ms': 0.8,
        'synonym_latency_ms': 1.2,
        'rag_latency_ms': 25.4,
        'cascade_latency_ms': 0.5,
        'v2_pipeline_latency_ms': 200.0,
        'feedback_latency_ms': 1.5,
        'total_latency_ms': 229.4
    }

OVERHEAD TOTAL: 29.4ms (hors V2 = 200ms)
✅ Objectif <50ms atteint !
```

---

## Feature Flags

### Configuration config.yaml

```yaml
rag_enhanced:
  enabled: false  # Master switch - DOIT être true pour activer

  slang_normalizer:
    enabled: true
    dict_path: "data/slang_dict.json"
    max_patterns: 200

  synonym_expander:
    enabled: true
    dict_path: "data/synonym_dict.json"
    max_synonyms: 6
    max_tokens_added: 15

  context_injector:
    enabled: true
    db_path: "data/session_history.db"
    default_window: 5
    max_window: 15
    fifo_limit: 15

  rag_3tier:
    enabled: false  # Progressive rollout - V2 par défaut
    collections:
      - "lyra_mcp_registry_v3"
      - "lyra_mcp_capabilities_v3"
      - "lyra_mcp_parameters_v3"
    cascade_strategy: "early_stop"

  confidence_cascader:
    enabled: true
    confidence_high: 0.85
    confidence_low: 0.60

  feedback_loop:
    enabled: true
    feedback_file: "data/feedback.json"
    window_size: 100
    suggestion_threshold: 3
    auto_enrich_threshold: 5
```

### Flags Granulaires

Chaque composant peut être activé/désactivé indépendamment :

| Composant | Enabled | Effet |
|-----------|---------|-------|
| **slang_normalizer** | false | Query passe sans normalisation slang |
| **synonym_expander** | false | Query passe sans expansion synonymes |
| **context_injector** | false | Pas d'injection contexte session |
| **rag_3tier** | false | Utilise SemanticRetriever V2 classique |
| **confidence_cascader** | false | Pas de décision par seuils, execute direct |
| **feedback_loop** | false | Pas d'enregistrement feedback |

---

## Scénarios d'Usage

### 1. Mode Production Complet

```yaml
rag_enhanced:
  enabled: true
  slang_normalizer: {enabled: true}
  synonym_expander: {enabled: true}
  context_injector: {enabled: true}
  rag_3tier: {enabled: true}         # 3-Tier activé
  confidence_cascader: {enabled: true}
  feedback_loop: {enabled: true}
```

**Résultat** : Tous les enrichissements actifs, overhead ~40-50ms.

### 2. Mode Progressive Rollout

```yaml
rag_enhanced:
  enabled: true
  slang_normalizer: {enabled: true}
  synonym_expander: {enabled: true}
  context_injector: {enabled: true}
  rag_3tier: {enabled: false}        # V2 RAG conservé
  confidence_cascader: {enabled: true}
  feedback_loop: {enabled: true}
```

**Résultat** : Enrichissement sans 3-Tier (fallback V2 RAG), overhead ~20-30ms.

### 3. Mode Testing Slang Only

```yaml
rag_enhanced:
  enabled: true
  slang_normalizer: {enabled: true}  # Seulement slang
  synonym_expander: {enabled: false}
  context_injector: {enabled: false}
  rag_3tier: {enabled: false}
  confidence_cascader: {enabled: false}
  feedback_loop: {enabled: false}
```

**Résultat** : Test slang isolé, overhead <1ms.

### 4. Mode V2 Pur (Backward Compat)

```yaml
rag_enhanced:
  enabled: false  # Master switch OFF
```

**Résultat** : Pipeline V2 classique sans aucun enrichissement, 0ms overhead.

---

## Métriques Tracking

### EnhancedPipelineResult.metrics

Chaque requête retourne des métriques détaillées :

```python
result = pipeline.process_query("démarre vm")
print(result.metrics)
# {
#     'slang_latency_ms': 0.8,
#     'synonym_latency_ms': 1.2,
#     'rag_latency_ms': 25.4,
#     'cascade_latency_ms': 0.5,
#     'context_latency_ms': 8.2,       # Si injecté
#     'v2_pipeline_latency_ms': 200.0,
#     'feedback_latency_ms': 1.5,
#     'total_latency_ms': 237.6
# }
```

### Interprétation

- **slang_latency_ms** : Temps normalisation slang (<1ms attendu)
- **synonym_latency_ms** : Temps expansion synonymes (<1ms attendu)
- **rag_latency_ms** : Temps recherche RAG (3-Tier ou V2, ~20-30ms)
- **cascade_latency_ms** : Temps décision cascade (<2ms attendu)
- **context_latency_ms** : Temps injection contexte (~10ms si déclenché)
- **v2_pipeline_latency_ms** : Temps pipeline V2 complet (EPHAISTOS + LYRA + HESTIA, ~100-500ms)
- **feedback_latency_ms** : Temps enregistrement feedback (<2ms attendu)
- **total_latency_ms** : Temps total requête (somme)

**Overhead Enhanced** = total - v2_pipeline  
**Objectif** : <50ms

---

## Exemples Utilisation

### 1. Créer et initialiser pipeline

```python
from lyra.rag_enhanced import EnhancedPipeline

# Mode Enhanced complet
pipeline = EnhancedPipeline(enabled=True)
pipeline.initialize()

# Mode V2 pur
pipeline_v2 = EnhancedPipeline(enabled=False)
pipeline_v2.initialize()
```

### 2. Traiter une requête

```python
result = pipeline.process_query("start preprod-09")

# Afficher résultat
print(result.response)
# "La VM preprod-09 est démarrée (IP: 192.168.122.146)"

# Afficher enrichissements
print(f"Normalized: {result.normalized_query}")   # "démarre preprod-09"
print(f"Expanded: {result.expanded_query}")       # "démarre lance boot..."
print(f"RAG source: {result.rag_source}")         # "capabilities"
print(f"Cascade: {result.cascade_action}")        # "execute"
print(f"Score: {result.rag_score}")               # 0.92

# Afficher métriques
print(f"Overhead: {result.metrics['total_latency_ms'] - result.metrics['v2_pipeline_latency_ms']:.1f}ms")
```

### 3. Hot reload configuration

```python
from lyra.rag_enhanced import RAGEnhancedConfig

# Modifier config
new_config = RAGEnhancedConfig()
new_config.slang_normalizer.enabled = False  # Désactiver slang

# Recharger
pipeline.reload_config(new_config)

# Prochaine requête utilisera la nouvelle config
result = pipeline.process_query("start vm")
print(result.normalized_query)  # "start vm" (pas de normalisation)
```

---

## Comparaison V2 vs Enhanced

| Aspect | V2 (Pipeline classique) | Enhanced (EnhancedPipeline) |
|--------|-------------------------|------------------------------|
| **Slang** | ❌ Non supporté | ✅ "start" → "démarre" |
| **Synonymes** | ❌ Non supporté | ✅ "vm" → "machine virtuelle..." |
| **Contexte** | ⚠️ Basique (session_memory) | ✅ Injection intelligente (SQLite) |
| **RAG** | 1 collection ChromaDB | 3 collections (entonnoir) |
| **Confiance** | ❌ Pas de seuils | ✅ 3 niveaux (HIGH/MEDIUM/LOW) |
| **Feedback** | ❌ Pas d'apprentissage | ✅ Apprentissage continu |
| **Overhead** | 0ms (baseline) | <50ms (objectif atteint) |
| **Backward compat** | N/A | ✅ 100% compatible si disabled |

---

## Troubleshooting

### Problème 1 : Overhead >50ms

**Symptôme** : `metrics['total_latency_ms']` trop élevé

**Causes possibles** :
- RAG 3-Tier lent (>40ms)
- Synonym expansion trop large (>15 tokens)
- Context injection systématique (devrait être on-demand)

**Solutions** :
1. Désactiver `rag_3tier` (fallback V2 RAG)
2. Réduire `synonym_expander.max_synonyms` (6 → 3)
3. Vérifier `confidence_cascader` fonctionne (pas d'injection si HIGH)

### Problème 2 : Slang/Synonym pas appliqués

**Symptôme** : `result.normalized_query == query original`

**Causes** :
- `rag_enhanced.enabled: false` dans config.yaml
- `slang_normalizer.enabled: false`
- Dictionnaire slang vide (`data/slang_dict.json`)

**Solutions** :
1. Vérifier `rag_enhanced.enabled: true`
2. Vérifier `slang_normalizer.enabled: true`
3. Vérifier `data/slang_dict.json` contient des entrées

### Problème 3 : Feedback pas enregistré

**Symptôme** : `result.feedback_recorded == False`

**Causes** :
- `feedback_loop.enabled: false`
- `result.tool_call is None` (pas d'action MCP)

**Solutions** :
1. Vérifier `feedback_loop.enabled: true`
2. Vérifier la requête génère bien un tool_call

---

## Prochaines Étapes

**SESSION 8 (P6.2)** : Tests E2E + Validation

12 scénarios E2E couvrant :
- HUE, CATT, TV, FEDORA, DENON, MERMAID
- Contexte multi-tour
- Cascader fallback
- Performance robustesse

---

**Dernière mise à jour** : 2026-02-13  
**SESSION 7 (P6.1)** - EnhancedPipeline  
**Maintenu par** : Claude Code
