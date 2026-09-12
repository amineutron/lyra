# Scénarios E2E - RAG Enhanced

Documentation des scénarios end-to-end testant le pipeline Enhanced complet.

## Vue d'Ensemble

Les tests E2E valident le workflow complet du pipeline EnhancedPipeline :

```
USER QUERY
    ↓
1. SlangNormalizer     (opt) <1ms
    ↓
2. SynonymExpander     (opt) <1ms
    ↓
3. RAG 3-Tier / V2     ~20-30ms
    ↓
4. ConfidenceCascader  <2ms
    ├─→ HIGH (>0.85) → EXECUTE
    ├─→ MEDIUM (0.60-0.85) → PROPOSE + Context (opt)
    └─→ LOW (<0.60) → FALLBACK
    ↓
5. ContextInjector     (on-demand) ~10ms
    ↓
6. Pipeline V2         (EPHAISTOS → LYRA → HESTIA)
    ↓
7. FeedbackLoop        <2ms
    ↓
ENHANCED RESULT
```

---

## Scénarios Implémentés

### Groupe 1 : Composants de Base

#### Scénario 1 : Slang Normalizer
**Query** : `"start preprod-09"`

**Workflow** :
- SlangNormalizer détecte "start" (anglicisme)
- Normalise → "démarre preprod-09"
- Pipeline V2 traite la query normalisée

**Assertions** :
```python
assert result.normalized_query == "démarre preprod-09"
assert result.metrics['slang_latency_ms'] < 1.0
```

#### Scénario 2 : Synonym Expander
**Query** : `"lance la vm de test"`

**Workflow** :
- SynonymExpander détecte "lance"
- Expands → "lance démarre boot vm de test machine serveur"
- RAG utilise la query étendue

**Assertions** :
```python
assert "démarre" in result.expanded_query or "machine" in result.expanded_query
assert result.metrics['synonym_latency_ms'] < 1.0
```

---

### Groupe 2 : Feature Flags

#### Scénario 3 : Pipeline Disabled
**Config** : `enabled=False`

**Workflow** :
- EnhancedPipeline fallback → Pipeline V2 pur
- Aucun enrichissement (Slang, Synonym, Context, Feedback)
- Overhead = 0ms

**Assertions** :
```python
assert result.normalized_query == query  # Inchangé
assert result.expanded_query == query    # Inchangé
assert not result.feedback_recorded
```

#### Scénario 4 : Component Toggling
**Config** : `slang_normalizer.enabled=True`, autres `enabled=False`

**Workflow** :
- Seulement Slang Normalizer actif
- Autres composants bypassés

**Assertions** :
```python
assert result.normalized_query != query  # Normalisé
assert result.expanded_query == result.normalized_query  # Pas d'expansion
```

---

### Groupe 3 : Performance

#### Scénario 5 : Overhead Composants
**Query** : `"démarre preprod-09"` (100x)

**Workflow** :
- Mesure latency de chaque composant
- Calcule overhead total = somme(slang + synonym + cascade + context + feedback)

**Assertions** :
```python
overhead = sum([slang_ms, synonym_ms, cascade_ms, context_ms, feedback_ms])
assert overhead < 50  # <50ms objectif SESSION 7
```

#### Scénario 6 : Slang + Synonym Performance
**Query** : 100 queries mixtes

**Workflow** :
- Test Slang + Synonym seulement (sans RAG/V2)
- Médiane latency sur 100 queries

**Assertions** :
```python
median_latency = sorted(latencies)[50]
assert median_latency < 5.0  # <5ms objectif
p95 = sorted(latencies)[95]
assert p95 < 10.0
```

---

### Groupe 4 : Context Injection

#### Scénario 7 : Context Multi-tour
**Session** : 3 tours (start → snapshot → stop)

**Workflow** :
```
Tour 1: "démarre preprod-09"
  → ContextDB.log_exchange(mcp_used="vm_start", server="FEDORA")

Tour 2: "fais un snapshot"
  → ContextInjector.should_inject() → True (ambiguïté backup vs snapshot)
  → Inject: [ctx: last_mcp=vm_start, last_server=FEDORA]
  → EPHAISTOS résout avec contexte

Tour 3: "arrête la vm"
  → Contexte: preprod-09 encore actif
  → EPHAISTOS : vm_name=preprod-09
```

**Assertions** :
```python
assert result2.should_inject_context is True
assert "preprod-09" in result2.tool_call['arguments'].values()
```

#### Scénario 8 : Context Fallback si High Confidence
**Query** : `"démarre preprod-09"` (high confidence)

**Workflow** :
- RAG score >0.85
- ConfidenceCascader → EXECUTE (pas besoin contexte)
- ContextInjector bypassed

**Assertions** :
```python
assert result.rag_score > 0.85
assert result.should_inject_context is False
```

---

### Groupe 5 : Confidence Cascade

#### Scénario 9 : HIGH Confidence → Execute
**Query** : `"vm_start preprod-09"` (exact match)

**Workflow** :
- RAG score 0.95 (registry hit exact)
- Cascade → EXECUTE direct
- Pas de confirmation utilisateur

**Assertions** :
```python
assert result.rag_score > 0.85
assert result.cascade_action == "execute"
```

#### Scénario 10 : MEDIUM Confidence → Propose
**Query** : `"fais un backup"` (ambigu backup_create vs vm_snapshot)

**Workflow** :
- RAG score 0.72 (2 outils proches)
- Cascade → PROPOSE options
- pending_args pour clarification

**Assertions** :
```python
assert 0.60 <= result.rag_score < 0.85
assert result.cascade_action == "propose"
assert len(result.pending_args) > 0 or result.tool_call
```

#### Scénario 11 : LOW Confidence → Fallback
**Query** : `"quel temps fait-il demain"` (hors scope)

**Workflow** :
- RAG score <0.60 (aucun MCP adapté)
- Cascade → FALLBACK LYRA
- Réponse conversationnelle

**Assertions** :
```python
assert result.rag_score < 0.60
assert result.cascade_action == "fallback"
assert result.query_type == QueryType.KNOWLEDGE
```

---

### Groupe 6 : Robustesse

#### Scénario 12 : Sessions Concurrentes
**Setup** : 2 sessions A (VM) et B (HUE) avec historiques séparés

**Workflow** :
```
Session A: vm_start preprod-09
Session B: hue.turn_on_group salon

Query A: "fais un snapshot" → Contexte: last_mcp=vm_start
Query B: "éteins tout" → Contexte: last_mcp=hue.turn_on_group
```

**Assertions** :
```python
history_a = context_db.get_last_exchanges("session_a", n=10)
history_b = context_db.get_last_exchanges("session_b", n=10)
assert 'vm_start' in [h['mcp_used'] for h in history_a]
assert 'hue.turn_on_group' in [h['mcp_used'] for h in history_b]
# Pas de mélange
assert 'vm_start' not in [h['mcp_used'] for h in history_b]
```

#### Scénario 13 : Edge Cases
**Queries** : empty, very long, special chars, unicode

**Workflow** :
- Pipeline gère gracieusement sans crash
- Retourne PipelineResult valide

**Assertions** :
```python
result = pipeline.process_query("", session_id)
assert result is not None

result = pipeline.process_query("démarre " + "vm " * 100, session_id)
assert result is not None

result = pipeline.process_query("vm-test_01@prod", session_id)
assert result is not None

result = pipeline.process_query("lumière 🔆", session_id)
assert result is not None
```

---

## Métriques Collectées

Chaque test E2E collecte les métriques suivantes dans `EnhancedPipelineResult.metrics` :

| Métrique | Description | Objectif |
|----------|-------------|----------|
| `slang_latency_ms` | Temps Slang Normalizer | <1ms |
| `synonym_latency_ms` | Temps Synonym Expander | <1ms |
| `rag_latency_ms` | Temps RAG retrieval | <30ms |
| `cascade_latency_ms` | Temps Confidence Cascader | <2ms |
| `context_latency_ms` | Temps Context Injector | <10ms |
| `v2_pipeline_latency_ms` | Temps Pipeline V2 (EPHAISTOS + LYRA + HESTIA) | ~100-200ms |
| `feedback_latency_ms` | Temps Feedback Loop | <2ms |
| **`total_latency_ms`** | **Temps total E2E** | **<250ms** |

---

## Matrice de Compatibilité

| Mode | Slang | Synonym | Context | RAG 3-Tier | Cascade | Feedback | Overhead |
|------|-------|---------|---------|------------|---------|----------|----------|
| **V2 Pur** (`enabled=False`) | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | 0ms |
| **Enhanced Léger** | ✓ | ✓ | ✗ | ✗ | ✓ | ✓ | <5ms |
| **Enhanced Complet** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | <50ms |

---

## Exécution des Tests E2E

```bash
# Tous les tests E2E
pytest tests/e2e/rag_enhanced/ -v

# Scénarios basiques seulement
pytest tests/e2e/rag_enhanced/test_e2e_basic_scenarios.py -v

# Scénarios performance
pytest tests/e2e/rag_enhanced/test_e2e_advanced.py::TestScenario13_PerformanceSlangSynonym -v

# Avec couverture
pytest tests/e2e/rag_enhanced/ --cov=lyra/rag_enhanced --cov-report=term-missing
```

---

## Limitations et Prochaines Étapes

### Limitations Actuelles

1. **Mocks Ollama** : EPHAISTOS et LYRA sont mockés, pas de vraie génération LLM
2. **Mocks MCP** : HESTIA execution mockée, pas d'appels MCP réels
3. **ChromaDB** : RAG 3-Tier mocké pour compatibilité Pydantic v2

### Tests Complémentaires (SESSION 9+)

- Tests E2E avec Ollama réel (nécessite Ollama running)
- Tests E2E avec MCP réels en environnement sandbox
- Tests de charge (100+ queries/sec)
- Tests de régression automatisés

### Validation Manuelle

Pour valider le workflow complet avec Ollama + MCP réels :

```bash
# Lancer Lyra avec RAG Enhanced
./run.sh --rag-enhanced

# Test manuel
>>> start preprod-09
# Vérifier normalisation Slang dans logs
# Vérifier expansion Synonym
# Vérifier tool_call correct

>>> fais un snapshot
# Vérifier context injection (last_mcp=vm_start)
```

---

**Dernière mise à jour** : 2026-02-13
**SESSION** : 8 (Tests E2E + Validation)
