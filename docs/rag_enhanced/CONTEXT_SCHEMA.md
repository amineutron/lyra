# Context Injector - Schema et Stratégie

Guide complet sur le système d'injection de contexte pour le RAG Enhanced.

## Vue d'Ensemble

Le **Context Injector** enrichit les requêtes utilisateur avec le contexte de session (historique récent) on-demand, basé sur l'**écart de score RAG** entre les 2 meilleurs résultats.

### Objectifs

- ✅ Résoudre l'ambiguïté RAG (top 2 MCP proches)
- ✅ Injecter contexte seulement quand nécessaire (on-demand)
- ✅ Historique persistant SQLite (FIFO 15 échanges/session)
- ✅ Performance <10ms (requête SQL + injection)

---

## Architecture

```
┌──────────────┐
│ Query User   │  "fais un backup"
└──────┬───────┘
       │
       ▼
┌────────────────────────┐
│ RAG Retrieval          │
│ top_1: backup_create   │ 0.72
│ top_2: vm_snapshot     │ 0.70  ← Écart 0.02 < 0.05
└────────┬───────────────┘
         │
         ▼
┌───────────────────────────┐
│ should_inject() ?         │
│ Écart 0.02 < 0.05         │
│ → inject 10 échanges      │
└────────┬──────────────────┘
         │
         ▼
┌────────────────────────────────────┐
│ ContextDB (SQLite)                 │
│ get_last_exchanges("123", n=10)    │
│ → Historique récent                │
└────────┬───────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────┐
│ inject() → Contexte enrichi              │
│ "[ctx: last_mcp=vm_start,                │
│  frequent_mcp=vm_start,                  │
│  last_server=FEDORA]"                    │
└────────┬─────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────┐
│ Query Enrichie                       │
│ "fais un backup [ctx: ...]"          │
└──────────────────────────────────────┘
         │
         ▼
    EPHAISTOS
```

---

## Schema SQLite

### Table: `session_history`

```sql
CREATE TABLE session_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user', 'lyra')),
    content TEXT NOT NULL,
    mcp_used TEXT,
    server_used TEXT,
    created_at INTEGER NOT NULL  -- Microsecondes (unicité garantie)
);

CREATE INDEX idx_session_created
    ON session_history(session_id, created_at DESC);
```

**Colonnes** :

| Colonne | Type | Description |
|---------|------|-------------|
| `id` | INTEGER | Clé primaire auto-incrémentée |
| `session_id` | TEXT | ID unique de session (ex: "123") |
| `role` | TEXT | "user" ou "lyra" (constraint CHECK) |
| `content` | TEXT | Contenu du message |
| `mcp_used` | TEXT | Outil MCP si action (ex: "vm_start") |
| `server_used` | TEXT | Serveur MCP (FEDORA, HUE, TV, etc.) |
| `created_at` | INTEGER | Timestamp en microsecondes |

**Index** :
- `idx_session_created` : Accélère `get_last_exchanges()` (requête fréquente)

### FIFO : Max 15 Échanges/Session

**Contrainte TOPO** : Max 15 échanges conservés par session.

**Mécanisme** : Auto-purge après chaque `log_exchange()`.

```python
def _enforce_fifo_limit(self, session_id: str, max_limit: int = 15):
    """Purge les plus anciens si > max_limit."""
    count = SELECT COUNT(*) FROM session_history WHERE session_id = ?

    if count > max_limit:
        to_delete = count - max_limit
        DELETE FROM session_history
        WHERE id IN (
            SELECT id FROM session_history
            WHERE session_id = ?
            ORDER BY created_at ASC
            LIMIT to_delete
        )
```

**Exemple** :
```
Log exchange 1, 2, ..., 15 → OK
Log exchange 16 → Purge exchange 1 (plus ancien)
Log exchange 17 → Purge exchange 2
...
```

---

## Stratégie d'Injection On-Demand

### Décision Basée sur Écart RAG

**Méthode** : `should_inject(rag_results: list[dict]) -> (bool, int)`

**Règles** :

| Écart Score | Injection | N Échanges | Raison |
|-------------|-----------|------------|--------|
| **> 0.10** | ❌ Non | 0 | Écart suffisant, pas d'ambiguïté |
| **0.05 - 0.10** | ✅ Oui | 5 | Ambiguïté modérée |
| **< 0.05** | ✅ Oui | 10 | Ambiguïté forte |

**Exemples** :

```python
# Exemple 1: Écart large → pas d'injection
rag_results = [
    {'tool_name': 'vm_start', 'score': 0.90},
    {'tool_name': 'vm_clone', 'score': 0.70}
]
should_inject, n = injector.should_inject(rag_results)
# → (False, 0) - Écart 0.20 > 0.10

# Exemple 2: Écart moyen → inject 5
rag_results = [
    {'tool_name': 'vm_start', 'score': 0.75},
    {'tool_name': 'vm_clone', 'score': 0.68}
]
should_inject, n = injector.should_inject(rag_results)
# → (True, 5) - Écart 0.07

# Exemple 3: Écart faible → inject 10
rag_results = [
    {'tool_name': 'backup_create', 'score': 0.72},
    {'tool_name': 'vm_snapshot', 'score': 0.70}
]
should_inject, n = injector.should_inject(rag_results)
# → (True, 10) - Écart 0.02 < 0.05
```

### Extraction Contexte

**Méthode** : `inject(query: str, session_id: str, n: int) -> str`

**Informations extraites** :

1. **last_mcp** : Dernier outil MCP utilisé
2. **frequent_mcp** : Outil le plus fréquent sur fenêtre N
3. **last_server** : Dernier serveur MCP (FEDORA/HUE/TV/CATT/DENON/MERMAID)

**Format** :
```
[ctx: last_mcp=vm_start, frequent_mcp=vm_start, last_server=FEDORA]
```

**Algorithme** :
```python
history = db.get_last_exchanges(session_id, n)  # Ordre DESC

last_mcp = None
last_server = None
mcp_counts = {}

for exchange in history:
    if exchange['mcp_used']:
        if last_mcp is None:  # Premier (plus récent)
            last_mcp = exchange['mcp_used']
            last_server = exchange['server_used']

        # Compter occurrences
        mcp_counts[exchange['mcp_used']] += 1

# MCP le plus fréquent
frequent_mcp = max(mcp_counts.items(), key=lambda x: x[1])[0]

context = f"[ctx: last_mcp={last_mcp}, frequent_mcp={frequent_mcp}, last_server={last_server}]"
return f"{query} {context}"
```

---

## Cas d'Usage

### Cas 1 : VM FEDORA - Ambiguïté "backup"

**Scénario** : Utilisateur demande "fais un backup" après avoir démarré une VM.

**Historique** :
```
1. user: "démarre preprod-09"
2. lyra: "VM démarrée" [mcp=vm_start, server=FEDORA]
```

**RAG Retrieval** :
```
top_1: backup_create (FEDORA) - 0.72
top_2: vm_snapshot (FEDORA) - 0.70
Écart: 0.02 < 0.05 → inject 10 échanges
```

**Injection** :
```python
injector.inject("fais un backup", session_id="123", n=10)
# → "fais un backup [ctx: last_mcp=vm_start, frequent_mcp=vm_start, last_server=FEDORA]"
```

**EPHAISTOS** : Utilise contexte pour choisir `vm_snapshot` (cohérent avec FEDORA).

### Cas 2 : Volume Ambiguïté (TV/Denon/Cast)

**Scénario** : Utilisateur dit "monte le volume" (ambigu : TV, Denon, ou Cast ?).

**Historique** :
```
1. user: "caste cette vidéo youtube"
2. lyra: "Vidéo castée" [mcp=cast_youtube, server=CATT]
```

**RAG Retrieval** :
```
top_1: cast.volume (CATT) - 0.75
top_2: tv.volume_up (TV) - 0.73
Écart: 0.02 < 0.05 → inject 10 échanges
```

**Injection** :
```python
injector.inject("monte le volume", session_id="123", n=10)
# → "monte le volume [ctx: last_mcp=cast_youtube, frequent_mcp=cast_youtube, last_server=CATT]"
```

**EPHAISTOS** : Choisit `cast.volume` grâce au contexte CATT.

### Cas 3 : Écart Large - Pas d'Injection

**Scénario** : Utilisateur demande "démarre preprod-09" (requête claire).

**RAG Retrieval** :
```
top_1: vm_start (FEDORA) - 0.92
top_2: vm_clone (FEDORA) - 0.65
Écart: 0.27 > 0.10 → pas d'injection
```

**Résultat** :
```python
should_inject, n = injector.should_inject(rag_results)
# → (False, 0)
# Query reste inchangée
```

---

## API ContextDB

### Initialisation

```python
from lyra.rag_enhanced import ContextDB

db = ContextDB("data/session_history.db")
```

### Log Exchange

```python
# Log échange user
db.log_exchange(
    session_id="123",
    role="user",
    content="démarre preprod-09",
    mcp_used=None,
    server_used=None
)

# Log échange lyra après exécution
db.log_exchange(
    session_id="123",
    role="lyra",
    content="VM démarrée (IP: 192.168.122.146)",
    mcp_used="vm_start",
    server_used="FEDORA"
)
```

### Récupérer Historique

```python
# 5 derniers échanges
history = db.get_last_exchanges("123", n=5)

# Format:
# [
#     {'id': 2, 'role': 'lyra', 'content': 'VM démarrée', 'mcp_used': 'vm_start', ...},
#     {'id': 1, 'role': 'user', 'content': 'démarre preprod-09', 'mcp_used': None, ...}
# ]
```

### Fermeture

```python
db.close()
```

---

## API ContextInjector

### Initialisation

```python
from lyra.rag_enhanced import ContextInjector

injector = ContextInjector()
# OU
injector = ContextInjector(enabled=False)  # Désactiver
```

### Décision Injection

```python
rag_results = [
    {'tool_name': 'backup_create', 'score': 0.72},
    {'tool_name': 'vm_snapshot', 'score': 0.70}
]

should_inject, n = injector.should_inject(rag_results)
# → (True, 10) si écart < 0.05
```

### Injection Contexte

```python
if should_inject:
    enriched = injector.inject("fais un backup", session_id="123", n=n)
    # → "fais un backup [ctx: last_mcp=vm_start, ...]"
```

### Log Exchange

```python
# Wrapper autour de ContextDB
injector.log_exchange("123", "user", "démarre vm", None, None)
injector.log_exchange("123", "lyra", "VM démarrée", "vm_start", "FEDORA")
```

---

## Intégration Pipeline

### Phase 3.5 : Après RAG, Avant EPHAISTOS

```
USER QUERY
    ↓
SlangNormalizer.normalize()    <1ms
    ↓
SynonymExpander.expand()       <1ms
    ↓
RAG3Tier.cascade_search()      ~20-30ms
    ↓
┌─────────────────────────────────────┐
│ ContextInjector.should_inject() ?  │ <1ms
│ Écart top_1 - top_2 < 0.10 ?       │
└────────┬────────────────────────────┘
         │ YES
         ▼
   ContextInjector.inject()           ~10ms
         ↓
EPHAISTOS.analyze()                   ~100-200ms
    ↓
HESTIA.execute()
    ↓
┌──────────────────────────────────┐
│ ContextInjector.log_exchange()  │ <2ms
│ - Log query user                │
│ - Log résultat lyra             │
└──────────────────────────────────┘
```

### Configuration

**`config.yaml`** :
```yaml
rag_enhanced:
  context_injector:
    enabled: false              # Activer en SESSION 7
    db_path: "data/session_history.db"
    default_window: 5           # N échanges par défaut
    max_window: 15              # Limite TOPO
    fifo_limit: 15              # Max échanges conservés
```

**Code** :
```python
from lyra.rag_enhanced import ContextInjector

injector = ContextInjector()

# Étape 1: RAG retrieval
rag_results = rag.cascade_search(query)

# Étape 2: Décision injection
should_inject, n = injector.should_inject(rag_results)

# Étape 3: Injection si nécessaire
if should_inject:
    query_enriched = injector.inject(query, session_id, n)
else:
    query_enriched = query

# Étape 4: EPHAISTOS
tool_call = ephaistos.analyze(query_enriched, rag_results)

# Étape 5: Log après exécution
injector.log_exchange(session_id, "user", query, None, None)
injector.log_exchange(session_id, "lyra", result, tool_call['name'], server)
```

---

## Tests

### Lancer les Tests

```bash
# Tests ContextDB
pytest tests/unit/rag_enhanced/test_context_db.py -v

# Tests ContextInjector
pytest tests/unit/rag_enhanced/test_context_injector.py -v

# Avec couverture
pytest tests/unit/rag_enhanced/test_context_*.py \
  --cov=lyra.rag_enhanced.context_db \
  --cov=lyra.rag_enhanced.context_injector \
  --cov-report=term
```

### Résultats SESSION 4

- **Tests** : 27 passés ✅ (12 ContextDB + 15 ContextInjector)
- **Couverture** : 93% ✅ (94% ContextDB + 92% ContextInjector)

---

## Performance

### Benchmarks

| Opération | Latence |
|-----------|---------|
| `log_exchange()` | <2ms |
| `get_last_exchanges(n=5)` | <5ms |
| `get_last_exchanges(n=10)` | <8ms |
| `should_inject()` | <1ms |
| `inject(n=5)` | ~5ms (SQL + extraction) |
| `inject(n=10)` | ~8ms |

**Total overhead** : <10ms (contexte on-demand)

### Optimisations

1. **Index SQL** : `idx_session_created` accélère requêtes
2. **FIFO auto** : Purge anciens échanges → DB légère
3. **Microsecondes** : Timestamps uniques garantis
4. **Lazy loading** : Singleton pour réutiliser connexion

---

## Troubleshooting

### Problème 1 : Contexte non injecté

**Symptôme** : `inject()` retourne query inchangée

**Causes possibles** :
- `enabled=False` dans config
- Historique vide pour session
- Écart RAG > 0.10

**Solution** : Vérifier `should_inject()` et historique DB

### Problème 2 : Ordre échanges incorrect

**Symptôme** : `last_mcp` ne correspond pas au dernier échange

**Cause** : Timestamps identiques (millisecondes)

**Solution** : Utiliser microsecondes (déjà implémenté)

### Problème 3 : DB verrouillée

**Symptôme** : `sqlite3.OperationalError: database is locked`

**Cause** : Plusieurs connexions simultanées

**Solution** : Utiliser singleton `get_context_db()`

---

## Changelog

### v0.1.0 (SESSION 4 - 2026-02-13)

- ✅ Implémentation initiale `ContextDB` (SQLite)
- ✅ Schema `session_history` avec FIFO 15 échanges
- ✅ Implémentation `ContextInjector`
- ✅ Stratégie on-demand basée sur écart RAG
- ✅ Format contexte compact `[ctx: ...]`
- ✅ 27 tests, 93% couverture
- ✅ Performance <10ms

---

## Prochaines Étapes

**SESSION 5** : RAG 3-Tier Collections (entonnoir séquentiel)

**SESSION 7** : Intégration dans pipeline.py avec feature flags

---

**Dernière mise à jour** : 2026-02-13
**Maintenu par** : Claude Code
**Questions** : Voir ARCHITECTURE.md, PROGRESS.md
