# Architecture RAG Enhanced

## Vue d'Ensemble

Le système RAG Enhanced enrichit le pipeline RAG V2 actuel avec 6 composants pour améliorer la précision de détection des outils MCP et réduire les ambiguïtés.

## Diagramme Flux

```
USER QUERY
    ↓
┌─────────────────────────┐
│ 1. SlangNormalizer      │  <1ms   (anglicismes → français)
│    "start" → "démarre"  │
└─────────────────────────┘
    ↓
┌─────────────────────────┐
│ 2. SynonymExpander      │  <1ms   (expansion synonymes)
│    "vm" + ["machine",   │
│         "serveur"]      │
└─────────────────────────┘
    ↓
┌─────────────────────────┐
│ 3. RAG 3-Tier           │  ~20-30ms (entonnoir séquentiel)
│    ┌─────────────────┐  │
│    │ Registry        │  │  → Serveur MCP (FEDORA/HUE/TV...)
│    └─────────────────┘  │
│           ↓             │
│    ┌─────────────────┐  │
│    │ Capabilities    │  │  → Outil (vm_start, hue.turn_on...)
│    └─────────────────┘  │
│           ↓             │
│    ┌─────────────────┐  │
│    │ Parameters      │  │  → Arguments (vm_name, brightness...)
│    └─────────────────┘  │
└─────────────────────────┘
    ↓
┌─────────────────────────┐
│ 4. ConfidenceCascader   │  <2ms   (décision selon score)
│    ├─ HIGH (>0.85)      │
│    │  → EXECUTE direct  │
│    ├─ MEDIUM (0.60-0.85)│
│    │  → PROPOSE options │
│    │  → ContextInjector?│
│    └─ LOW (<0.60)       │
│       → FALLBACK LYRA   │
└─────────────────────────┘
    ↓
┌─────────────────────────┐
│ 5. ContextInjector      │  ~10ms  (si écart <0.10)
│    (on-demand)          │
│    SQLite session       │
│    history              │
│    → last_mcp           │
│    → frequent_mcp       │
└─────────────────────────┘
    ↓
┌─────────────────────────┐
│ 6. EPHAISTOS            │  ~100-200ms (LLM)
│    (analyse args)       │
└─────────────────────────┘
    ↓
┌─────────────────────────┐
│ 7. HESTIA               │  ~100-500ms (MCP)
│    (exécution)          │
└─────────────────────────┘
    ↓
┌─────────────────────────┐
│ 8. FeedbackLoop         │  <2ms
│    (record success/fail)│
└─────────────────────────┘
    ↓
┌─────────────────────────┐
│ 9. LYRA                 │  ~50-100ms (LLM)
│    (format response)    │
└─────────────────────────┘
    ↓
RESULT

TOTAL OVERHEAD: ~40-50ms (hors LLM/MCP)
```

## Composants

### 1. SlangNormalizer (P1)

**Objectif** : Normaliser anglicismes et argot en français standard.

**Fonctionnement** :
- Dict JSON `slang_dict.json` (max 200 patterns)
- Match le plus long d'abord (ex: "backup manager" avant "backup")
- Case-insensitive
- Latence : <1ms

**Exemple** :
```
Input:  "start la vm preprod"
Output: "démarre la vm preprod"
```

### 2. SynonymExpander (P2)

**Objectif** : Enrichir la requête avec synonymes pour améliorer le recall RAG.

**Fonctionnement** :
- Dict JSON `synonym_dict.json` (max 80 keywords)
- Max 6 synonymes par mot-clé
- Max 15 tokens ajoutés total
- Latence : <1ms

**Exemple** :
```
Input:  "allume la lumière"
Output: "allume active démarre la lumière éclairage lampe"
```

### 3. RAG 3-Tier (P4)

**Objectif** : Entonnoir séquentiel avec filtrage metadata pour réduire le scope à chaque étape.

**Architecture** :
- **Collection 1 : Registry** (6 chunks, 1 par serveur MCP)
  - Métadata : `server_name`, `tool_count`, `category`
  - Document : "FEDORA (17 outils): VM KVM et backups. Keywords: vm, backup, snapshot..."

- **Collection 2 : Capabilities** (85 chunks, 1 par outil)
  - Métadata : `tool_name`, `server_name`, `capabilities`
  - Document : "vm_start: Démarre une VM KVM. Use cases: reboot, reprise après maintenance..."

- **Collection 3 : Parameters** (85 chunks, 1 par outil)
  - Métadata : `tool_name`, `required_params`, `optional_params`
  - Document : "vm_clone: Paramètres: source_vm (string), new_vm_name (string), start (bool)..."

**Stratégie Entonnoir** :
```python
# Étape 1: Registry → Identifier SERVEUR
registry_results = search_registry(query, top_k=3)
best_server = registry_results[0].metadata['server_name']  # Ex: "FEDORA"

# Étape 2: Capabilities → Filtrer par server_name → Identifier OUTIL
capabilities_results = search_capabilities(
    query,
    top_k=10,
    filter_metadata={'server_name': best_server}  # FILTRAGE
)
best_tool = capabilities_results[0].metadata['tool_name']  # Ex: "vm_start"

# Étape 3: Parameters → Filtrer par tool_name → Retourner PARAMÈTRES
parameters_results = search_parameters(
    query,
    top_k=1,
    filter_metadata={'tool_name': best_tool}  # FILTRAGE
)
```

**Latence** : ~20-30ms (≤ V2 + 20%)

### 4. ContextInjector (P3)

**Objectif** : Injecter contexte session quand RAG est ambiguë (écart <0.10 entre top 2).

**Fonctionnement** :
- SQLite `session_history.db`
- FIFO : max 15 échanges par session
- Injection on-demand selon seuil
- Format : `[ctx: last_mcp=vm_start, frequent_mcp=vm_clone, last_server=FEDORA]`

**Seuils** :
- Écart > 0.10 : pas d'injection (clair)
- Écart 0.05-0.10 : inject 5 derniers échanges
- Écart < 0.05 : inject 10 derniers échanges (ambiguïté forte)

**Latence** : <10ms (SQLite query)

### 5. ConfidenceCascader (P5)

**Objectif** : Décider l'action selon le score RAG.

**Seuils** :
- **HIGH (>0.85)** : EXECUTE direct
- **MEDIUM (0.60-0.85)** : PROPOSE options + inject context si écart <0.10
- **LOW (<0.60)** : FALLBACK LYRA (conversation)

**Latence** : <2ms

### 6. FeedbackLoop (P5)

**Objectif** : Apprentissage continu basé sur succès/échecs.

**Fonctionnalités** :
- Enregistrer chaque interaction (query, tool, score, success)
- Suggestion enrichissement après 3 échecs
- Auto-enrichissement après 5 échecs
- **IMPORTANT** : Enrichit dictionnaires (slang_dict, synonym_dict), **PAS** les embeddings ChromaDB
- Garde-fous :
  - Rotation si dict plein (200 slang, 80 synonyms)
  - Promotion après 50 hits (feedback temp → permanent)
  - Rollback auto si taux bon MCP baisse >20%

**Latence** : <2ms overhead

## Performance Budget

| Composant | Latence Max | Actuel V2 | Budget Enhanced |
|-----------|-------------|-----------|-----------------|
| SlangNormalizer | <1ms | - | +1ms |
| SynonymExpander | <1ms | - | +1ms |
| RAG Retrieval | ~20-30ms | ~25ms | ~30ms (+20%) |
| ContextInjector | <10ms | - | +10ms (si trigger) |
| ConfidenceCascader | <2ms | - | +2ms |
| FeedbackLoop | <2ms | - | +2ms |
| **TOTAL OVERHEAD** | **<50ms** | **~25ms** | **~75ms** |

**Note** : Overhead acceptable car le goulot est EPHAISTOS (~200ms) et HESTIA (~500ms).

## Feature Flags

Configuration granulaire via `config.yaml` :

```yaml
rag_enhanced:
  enabled: false  # Master switch

  slang_normalizer:
    enabled: false
  synonym_expander:
    enabled: false
  context_injector:
    enabled: false
  rag_3tier:
    enabled: false  # Progressive rollout
  feedback_loop:
    enabled: false
  confidence_cascader:
    enabled: false  # Dépend de feedback_loop

  metrics:
    enabled: true
```

## Backward Compatibility

- V2 pipeline **unchanged** si `rag_enhanced.enabled = false`
- Tous les tests V2 passent sans modification
- Migration progressive composant par composant

## Sessions d'Implémentation

Voir `PROGRESS.md` pour le tracking détaillé des 8 sessions (P0-P6.2).

## Diagramme Dépendances

```
SESSION 1 (P0) : Infrastructure
    │
    ├─→ SESSION 2 (P1) : SlangNormalizer
    ├─→ SESSION 3 (P2) : SynonymExpander
    ├─→ SESSION 4 (P3) : ContextInjector
    ├─→ SESSION 5 (P4) : RAG 3-Tier
    └─→ SESSION 6 (P5) : FeedbackLoop + Cascader
         │
         └─→ SESSION 7 (P6.1) : Pipeline Integration
              │
              └─→ SESSION 8 (P6.2) : Tests E2E
```

Sessions 2-5 **parallélisables** après SESSION 1.

## Références

- **TOPO Spécification** : Plan détaillé 8 sessions
- **PROGRESS.md** : Tracking implémentation
- **tests/unit/rag_enhanced/** : Tests unitaires par composant
- **tests/integration/rag_enhanced/** : Tests intégration
- **tests/e2e/rag_enhanced/** : 12 scénarios E2E
