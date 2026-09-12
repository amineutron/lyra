# Guide d'Extension - Dictionnaire Slang

## Vue d'Ensemble

Le **Slang Normalizer** convertit les anglicismes et l'argot en français standard pour améliorer la détection des outils MCP.

**Fichier** : `data/slang_dict.json`

**Limite** : 200 patterns maximum (TOPO)

**Stratégie** : Match le plus long d'abord, case-insensitive

## Structure du Dictionnaire

```json
{
  "_comment_section": "Description de la section (ignoré)",

  "pattern_court": "remplacement",
  "pattern plus long": "remplacement avec plusieurs mots",

  "_section_suivante": "Autre section..."
}
```

**Règles** :
- Clés commençant par `_` sont ignorées (commentaires)
- Patterns : anglicisme ou argot
- Remplacements : français standard
- Case-insensitive (automatique)
- Word boundaries automatiques (match mots complets uniquement)

## Dictionnaire Actuel

### Sections

1. **VM/FEDORA** (17 outils MCP)
   - Actions : start, stop, kill, boot, shutdown, reboot, restart
   - Commandes : backup, restore, clone, snapshot, check, verify, list, show
   - Multi-mots : "backup manager", "vm controller"

2. **HUE** (24 outils MCP)
   - Actions : switch, turn on/off, cut, dim, brighten
   - Entités : light, lamp, bulb, brightness, color, scene

3. **TV** (14 outils MCP)
   - Entités : tv, channel, mute/unmute, app, launch

4. **CATT** (15 outils MCP)
   - Actions : cast, stream, play, pause, resume, seek
   - Entités : video, movie, music, url

5. **DENON** (10 outils MCP)
   - Entités : amp, amplifier, receiver, input, source

6. **MERMAID** (5 outils MCP)
   - Entités : diagram, chart, graph, flowchart

7. **Actions communes**
   - Verbes : run, execute, do, make, create, delete, remove

8. **Mots courants**
   - Expressions : all, everything, please, thanks, yes, no, ok

## Ajouter une Entrée

### 1. Pattern Simple

```json
{
  "halt": "arrête"
}
```

**Résultat** :
```
Input:  "halt the vm"
Output: "arrête the vm"
```

### 2. Pattern Multi-Mots

```json
{
  "power cycle": "redémarre"
}
```

**Résultat** :
```
Input:  "power cycle preprod-09"
Output: "redémarre preprod-09"
```

**Important** : Les patterns longs ont priorité. Si vous avez :
```json
{
  "backup": "sauvegarde",
  "backup manager": "gestionnaire de sauvegarde"
}
```

Alors "backup manager" matchera AVANT "backup" seul.

### 3. Patterns Spécifiques à un MCP

Pour ajouter des patterns pour un nouveau serveur MCP :

```json
{
  "_section_nouveau_mcp": "Description du nouveau serveur",

  "pattern1": "traduction1",
  "pattern2": "traduction2"
}
```

## Stratégie de Match

### Word Boundaries (frontières de mots)

Le normalizer utilise des **word boundaries** (`\b` en regex) pour éviter les matches partiels.

**Exemple** :
```json
{
  "cast": "diffuse"
}
```

**Comportement** :
```
✅ "cast video"     → "diffuse video"   (match mot complet)
❌ "broadcast"      → "broadcast"       (pas de match partiel)
✅ "cast!"          → "diffuse!"        (ponctuation OK)
```

### Ordre de Traitement

1. **Tri par longueur décroissante** : Patterns longs matchent d'abord
2. **Compilation regex** : Optimisé au démarrage
3. **Application séquentielle** : Un pattern à la fois

**Exemple** :
```json
{
  "power": "puissance",          // Longueur 5
  "power on": "allume",          // Longueur 8 → matche D'ABORD
  "power off": "éteins"          // Longueur 9 → matche EN PREMIER
}
```

Ordre d'application :
1. "power off" (9 chars)
2. "power on" (8 chars)
3. "power" (5 chars)

## Cas d'Usage

### Cas 1 : Nouvel outil MCP

**Situation** : Vous ajoutez un nouveau serveur MCP "docker-mcp"

**Action** :
```json
{
  "_section_docker": "Docker MCP - 12 outils",

  "container": "conteneur",
  "containers": "conteneurs",
  "image": "image",
  "build": "construit",
  "run container": "lance conteneur",
  "stop container": "arrête conteneur"
}
```

### Cas 2 : Feedback utilisateurs

**Situation** : Les utilisateurs disent souvent "kick" au lieu de "redémarre"

**Action** :
```json
{
  "kick": "redémarre"
}
```

### Cas 3 : Expressions idiomatiques

**Situation** : Expressions françaises argotiques

**Action** :
```json
{
  "balance": "diffuse",      // "balance la vidéo" → "diffuse la vidéo"
  "choppe": "récupère",      // "choppe le fichier" → "récupère le fichier"
  "pète": "supprime"         // "pète la vm" → "supprime la vm"
}
```

## Limites et Contraintes

### Limite : 200 Patterns

**Actuel** : ~100 patterns utilisés

**Disponible** : ~100 patterns supplémentaires

**Si limite atteinte** :
1. Supprimer patterns rarement utilisés
2. Fusionner patterns similaires
3. Utiliser Feedback Loop (SESSION 6) pour rotation automatique

### Performance : <1ms

**Actuel** : ~0.003ms par requête (tests validés)

**Optimisations** :
- Compilation regex au démarrage
- Tri par longueur pré-calculé
- Pas de chargement dynamique

**Si dégradation** :
- Vérifier nombre de patterns (idéal : <150)
- Profiler avec `pytest --benchmark`

### Case-Insensitive

**Automatique** : Les patterns matchent quelle que soit la casse

**Exemple** :
```
Input:  "START the vm"
Output: "démarre the vm"  (tout en minuscules)
```

**Note** : La sortie est toujours en minuscules pour uniformité.

## Tests

### Tester une Nouvelle Entrée

```python
from lyra.rag_enhanced.slang_normalizer import SlangNormalizer

normalizer = SlangNormalizer()

# Test
result = normalizer.normalize("power cycle my vm")
assert result == "redémarre my vm"
```

### Tester avec Dictionnaire Custom

```python
custom_dict = {
    "foo": "bar",
    "hello world": "bonjour monde"
}

normalizer = SlangNormalizer(custom_dict=custom_dict)
result = normalizer.normalize("foo hello world")
# → "bar bonjour monde"
```

### Benchmark Performance

```bash
# Avec pytest-benchmark
pytest tests/unit/rag_enhanced/test_slang_normalizer.py::test_normalize_performance -v

# Sans pytest-benchmark (test manuel)
pytest tests/unit/rag_enhanced/test_slang_normalizer.py::test_normalize_performance_manual -v
```

## Contribution

### Process d'Ajout

1. **Identifier le besoin** : Logs, feedback utilisateurs, nouveaux outils MCP
2. **Ajouter au dictionnaire** : `data/slang_dict.json`
3. **Tester manuellement** :
   ```python
   from lyra.rag_enhanced import SlangNormalizer
   normalizer = SlangNormalizer()
   print(normalizer.normalize("votre requête"))
   ```
4. **Vérifier performance** :
   ```bash
   pytest tests/unit/rag_enhanced/test_slang_normalizer.py::test_normalize_performance_manual -v
   ```
5. **Commit** :
   ```bash
   git add data/slang_dict.json
   git commit -m "slang: ajout pattern 'xxx' pour MCP yyy"
   ```

### Bonnes Pratiques

✅ **DO** :
- Trier par sections (par MCP)
- Utiliser commentaires `_section_xxx`
- Patterns courts et clairs
- Tester avec vraies requêtes utilisateurs
- Vérifier word boundaries (pas de matches partiels)

❌ **DON'T** :
- Dépasser 200 patterns
- Patterns ambigus ("test" pourrait être "teste" ou "essai")
- Remplacements trop longs (max 4-5 mots)
- Duplicatas (vérifier d'abord si pattern existe)

## Intégration Pipeline

Le Slang Normalizer s'intègre dans le pipeline RAG Enhanced :

```
USER QUERY
    ↓
[SlangNormalizer]  <-- SESSION 2 (ce module)
    ↓
[SynonymExpander]
    ↓
[RAG 3-Tier]
    ↓
...
```

**Activation** :
```yaml
# config.yaml
rag_enhanced:
  slang_normalizer:
    enabled: true
    dict_path: "data/slang_dict.json"
    max_patterns: 200
```

## Troubleshooting

### Problème : Pattern ne matche pas

**Symptôme** : "start vm" n'est pas normalisé

**Solution** :
1. Vérifier que pattern existe dans `slang_dict.json`
2. Vérifier la casse (automatiquement géré, mais vérifier quand même)
3. Tester en isolation :
   ```python
   normalizer = SlangNormalizer()
   print(normalizer.slang_dict.get("start"))  # Devrait afficher "démarre"
   ```

### Problème : Performance dégradée

**Symptôme** : Latence >1ms

**Solution** :
1. Compter les patterns :
   ```python
   normalizer = SlangNormalizer()
   print(normalizer.get_stats())
   ```
2. Si >150 patterns, envisager nettoyage
3. Profiler :
   ```bash
   pytest tests/unit/rag_enhanced/test_slang_normalizer.py::test_normalize_performance_manual -v
   ```

### Problème : Match partiel

**Symptôme** : "broadcast" devient "diffusecast"

**Cause** : Les word boundaries sont activées par défaut, ce problème ne devrait PAS arriver.

**Vérification** :
```python
normalizer = SlangNormalizer()
result = normalizer.normalize("broadcast")
print(result)  # Devrait être "broadcast" (inchangé)
```

## Références

- **Code** : `lyra/rag_enhanced/slang_normalizer.py`
- **Tests** : `tests/unit/rag_enhanced/test_slang_normalizer.py`
- **Config** : `lyra/rag_enhanced/config.py` (SlangNormalizerConfig)
- **Dict** : `data/slang_dict.json`

---

**Auteur** : Claude Code (Sonnet 4.5)
**Session** : SESSION 2 (P1)
**Version** : 0.2.0
**Date** : 2026-02-13
