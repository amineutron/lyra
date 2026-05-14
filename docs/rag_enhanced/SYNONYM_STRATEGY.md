# Synonym Expander - Stratégie d'Expansion

Guide complet sur la stratégie d'expansion de synonymes pour le RAG Enhanced.

## Vue d'Ensemble

Le **Synonym Expander** enrichit les requêtes utilisateur en ajoutant des synonymes depuis un dictionnaire custom, améliorant ainsi le recall du système RAG.

### Objectifs

- ✅ Améliorer le recall RAG (plus de résultats pertinents)
- ✅ Gérer les variations linguistiques (français formel/informel)
- ✅ Rester performant (<1ms par requête)
- ✅ Respecter les limites TOPO (6 syn/mot, 15 tokens ajoutés max)

---

## Architecture

```
┌──────────────┐
│ Query User   │  "vm preprod"
└──────┬───────┘
       │
       ▼
┌──────────────────────┐
│ Synonym Expander     │
│ ┌──────────────────┐ │
│ │ Load Dict JSON   │ │  data/synonym_dict.json
│ │ Filter Comments  │ │  (skip keys starting with "_")
│ │ Lookup           │ │  vm → [machine, serveur, instance, virtuelle]
│ │ Limit Synonyms   │ │  max 6 per keyword (TOPO)
│ │ Limit Total      │ │  max 15 tokens added (TOPO)
│ │ Skip Stopwords   │ │  le, la, de, ...
│ └──────────────────┘ │
└──────┬───────────────┘
       │
       ▼
┌──────────────────────────────────────┐
│ Expanded Query                       │
│ "vm machine serveur instance         │
│  virtuelle preprod"                  │
└──────────────────────────────────────┘
```

---

## Stratégie d'Expansion

### 1. Chargement du Dictionnaire

**Fichier** : `data/synonym_dict.json`

**Format** :
```json
{
  "_comment_vm": "Section VM/FEDORA",
  "vm": ["machine", "serveur", "instance", "virtuelle"],
  "backup": ["sauvegarde", "copie", "archive"],

  "_comment_hue": "Section Hue",
  "lumière": ["éclairage", "lampe", "ampoule"]
}
```

**Règles** :
- Clés commençant par `"_"` → ignorées (commentaires)
- Valeurs doivent être des listes
- Max 6 synonymes par mot-clé (limite TOPO)

### 2. Expansion Étape par Étape

```python
def expand(query: str) -> str:
    """
    1. Split query en mots
    2. Pour chaque mot non-stopword:
        a. Lookup dans dict (case-insensitive)
        b. Ajouter max 6 synonymes (limite TOPO)
        c. Respecter limite 15 tokens ajoutés
    3. Retourner: "query original" + " " + "synonymes"
    """
```

**Exemple** :
```
Input:  "vm preprod"
Lookup: "vm" → ["machine", "serveur", "instance", "virtuelle"]
        "preprod" → (aucun match)
Output: "vm machine serveur instance virtuelle preprod"
```

### 3. Stopwords Français

**Liste** : `le`, `la`, `les`, `un`, `une`, `de`, `du`, `à`, `au`, `et`, `ou`, `mais`, `ce`, `mon`, `en`, `dans`, `sur`, `qui`, `que`...

**Raison** : Éviter d'ajouter des synonymes inutiles pour les mots de liaison.

**Exemple** :
```
Input:  "allume la lumière"
        ↓
        "allume" → lookup (✓)
        "la"     → stopword (skip)
        "lumière" → lookup (✓)
        ↓
Output: "allume active éclaire la lumière lampe ampoule"
```

---

## Limites TOPO

### Max 6 Synonymes par Mot-Clé

**Contrainte** : `SYNONYM_MAX_PER_KEYWORD = 6`

**Raison** : Éviter le bruit sémantique excessif.

**Exemple** :
```json
{
  "vm": ["machine", "serveur", "instance", "virtuelle", "hôte", "nœud"]
}
```
→ Si le mot "vm" a 10 synonymes dans le dict, seuls les 6 premiers seront utilisés.

### Max 15 Tokens Ajoutés au Total

**Contrainte** : `SYNONYM_MAX_TOKENS_ADDED = 15`

**Raison** : Limiter la taille de la requête expansée pour ne pas dégrader la performance RAG.

**Exemple** :
```
Input:  "allume toutes les lumières du salon"
Tokens: 6 mots originaux
Ajout:  Max 15 tokens de synonymes
Total:  Max 21 tokens dans la query expansée
```

Si plus de 15 synonymes seraient ajoutés, l'expansion s'arrête à 15.

---

## Dictionnaire Synonym

### Structure

Le dictionnaire est organisé par **sections MCP** :

| Section | Description | Keywords |
|---------|-------------|----------|
| `_section_vm_fedora` | VM et Backups | vm, backup, snapshot, clone, démarre, arrête, liste |
| `_section_hue` | Philips Hue | lumière, allume, éteins, luminosité, couleur, scène |
| `_section_tv` | TV Philips | télé, volume, lance, chaîne |
| `_section_cast` | CATT Cast | diffuse, vidéo, pause |
| `_section_denon` | Denon Home Cinema | ampli, source |
| `_section_mermaid` | Mermaid Diagrams | diagramme |
| `_section_common_verbs` | Verbes d'action | crée, affiche, change, configure |
| `_section_common_nouns` | Noms communs | état, configuration, fichier, système |
| `_section_adjectives` | Adjectifs | tout, rapide, lent |

### Exemples Annotés

```json
{
  "_section_vm_fedora": "VM et Backups (FEDORA MCP - 17 outils)",
  "vm": ["machine", "serveur", "instance", "virtuelle"],
  "backup": ["sauvegarde", "copie", "archive"],
  "snapshot": ["instantané", "image", "capture"],
  "clone": ["duplique", "copie", "reproduit"],
  "démarre": ["lance", "boot", "active"],
  "arrête": ["stop", "coupe", "ferme"],
  "liste": ["affiche", "montre", "énumère"],

  "_section_hue": "Philips Hue (HUE MCP - 24 outils)",
  "lumière": ["éclairage", "lampe", "ampoule"],
  "lumières": ["éclairages", "lampes", "ampoules"],
  "allume": ["active", "démarre", "éclaire"],
  "éteins": ["coupe", "désactive", "ferme"],
  "luminosité": ["brightness", "intensité", "éclairage"],

  "_section_common_verbs": "Verbes d'action",
  "crée": ["fait", "génère", "construit"],
  "affiche": ["montre", "présente", "liste"],
  "change": ["modifie", "ajuste", "règle"]
}
```

### Extension du Dictionnaire

#### Ajouter un Nouveau Mot-Clé

1. Identifier la section appropriée (ou créer une nouvelle)
2. Ajouter l'entrée avec max 6 synonymes
3. Tester avec `pytest tests/unit/rag_enhanced/test_synonym_expander.py`

**Exemple** :
```json
{
  "_section_fedora": "...",
  "restaure": ["récupère", "rétablit", "recharge"]
}
```

#### Vérifier les Limites

Avant de commit, vérifier :
```bash
# Total keywords ≤ 80 (limite TOPO)
python -c "
import json
with open('data/synonym_dict.json') as f:
    data = json.load(f)
    keywords = [k for k in data if not k.startswith('_')]
    print(f'Total keywords: {len(keywords)} (max 80)')
"

# Max 6 synonymes par keyword
python -c "
import json
with open('data/synonym_dict.json') as f:
    data = json.load(f)
    for k, v in data.items():
        if not k.startswith('_') and len(v) > 6:
            print(f'⚠️  {k} a {len(v)} synonymes (max 6)')
"
```

---

## Performance

### Benchmarks

**Target** : <1ms par requête

**Résultats SESSION 3** :
```
Médiane: 0.0287ms par requête
P95: 0.0450ms
```

→ **33x plus rapide** que requis ✅

### Optimisations

1. **Chargement unique** : Dict chargé une fois au `__init__`
2. **Lookup O(1)** : Dict Python natif (hash table)
3. **No regex** : Split simple sur espaces
4. **Early stop** : Arrêt dès que limite 15 tokens atteinte

---

## Cas d'Usage

### Cas 1 : VM FEDORA

**Input** : `"lance la vm preprod"`

**Process** :
- `"lance"` → lookup → `["démarre", "boot", "active"]`
- `"la"` → stopword (skip)
- `"vm"` → lookup → `["machine", "serveur", "instance", "virtuelle"]`
- `"preprod"` → no match

**Output** : `"lance démarre boot active la vm machine serveur instance virtuelle preprod"`

**RAG Impact** : Meilleur recall (match sur "démarre", "machine", etc.)

### Cas 2 : Hue Lights

**Input** : `"allume la lumière du salon"`

**Process** :
- `"allume"` → `["active", "démarre", "éclaire"]`
- `"la"` → stopword
- `"lumière"` → `["éclairage", "lampe", "ampoule"]`
- `"du"` → stopword
- `"salon"` → no match

**Output** : `"allume active démarre éclaire la lumière éclairage lampe ampoule du salon"`

**RAG Impact** : Match sur specs mentionnant "éclairage", "lampe"

### Cas 3 : Limite Max Tokens

**Input** : `"allume toutes les lumières bleues du salon et de la chambre"`

**Process** :
- Tokens originaux : 11
- Synonymes possibles : ~20 tokens
- Limite : 15 tokens ajoutés
- → Arrêt après 15 premiers synonymes

**Output** : ~26 tokens total (11 + 15)

---

## Intégration Pipeline

### Phase 2 : Après Slang Normalizer

```
USER QUERY
    ↓
SlangNormalizer.normalize()    <1ms
    ↓ "start vm" → "démarre vm"
SynonymExpander.expand()       <1ms
    ↓ "démarre vm machine serveur..."
RAG3Tier.cascade_search()      ~20-30ms
    ↓
EPHAISTOS.analyze()            ~100-200ms
    ↓
HESTIA.execute()
```

### Configuration

**`config.yaml`** :
```yaml
rag_enhanced:
  synonym_expander:
    enabled: false              # Activer en SESSION 7
    dict_path: "data/synonym_dict.json"
    max_synonyms: 6             # Limite TOPO
    max_tokens_added: 15        # Limite TOPO
```

**Code** :
```python
from lyra.rag_enhanced import SynonymExpander

expander = SynonymExpander()
expanded_query = expander.expand(normalized_query)
```

---

## Tests

### Lancer les Tests

```bash
# Tests unitaires
pytest tests/unit/rag_enhanced/test_synonym_expander.py -v

# Avec couverture
pytest tests/unit/rag_enhanced/test_synonym_expander.py \
  --cov=lyra.rag_enhanced.synonym_expander \
  --cov-report=term-missing

# Performance
pytest tests/unit/rag_enhanced/test_synonym_expander.py::TestSynonymExpander::test_expand_performance_manual -v
```

### Résultats SESSION 3

- **Tests** : 24 passés, 1 skipped ✅
- **Couverture** : 91% ✅ (>90% requis)
- **Performance** : 0.0287ms/requête ✅ (<1ms requis)

---

## Troubleshooting

### Problème 1 : Query expansée trop longue

**Symptôme** : Query de 50+ tokens après expansion

**Cause** : Trop de synonymes ajoutés

**Solution** :
- Réduire `max_tokens_added` dans config
- Ou : Réduire nombre de synonymes dans le dict

### Problème 2 : Recall pas amélioré

**Symptôme** : RAG score identique avant/après expansion

**Cause** : Synonymes pas pertinents pour les specs MCP

**Solution** :
- Analyser les specs MCP : quels termes sont utilisés ?
- Ajuster le dictionnaire pour coller aux specs
- Exemple : si specs parlent de "instance", ajouter "instance" comme synonyme de "vm"

### Problème 3 : Performance dégradée

**Symptôme** : Expansion prend >5ms

**Cause** : Dictionnaire trop large ou regex complexe

**Solution** :
- Vérifier taille dict (≤80 keywords)
- Éviter regex dans expand() (utiliser dict natif)
- Profiler avec `cProfile` si nécessaire

---

## Métriques

### Dictionnaire

**Stats actuelles** :
```
Total keywords: ~40
Avg synonyms/keyword: 3.5
Max synonyms: 6
```

### Performance

```
Latence médiane: 0.0287ms
P95: 0.0450ms
P99: 0.0650ms
```

---

## Changelog

### v0.1.0 (SESSION 3 - 2026-02-13)

- ✅ Implémentation initiale `SynonymExpander`
- ✅ Dictionnaire 40+ keywords (VM, HUE, TV, CATT, DENON, MERMAID)
- ✅ Respect limites TOPO (6 syn/mot, 15 tokens ajoutés)
- ✅ Stopwords français
- ✅ 24 tests, 91% couverture
- ✅ Performance 0.0287ms/requête

---

## Prochaines Étapes

**SESSION 4** : Context Injector (SQLite session history)

**SESSION 7** : Intégration dans pipeline.py avec feature flags

**Future** : Feedback Loop pourra suggérer ajout de synonymes après 3-5 échecs

---

**Dernière mise à jour** : 2026-02-13
**Maintenu par** : Claude Code
**Questions** : Voir ARCHITECTURE.md, PROGRESS.md
