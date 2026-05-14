# TOPO FINAL : Migration Enrichissement Côté Indexation

**Date** : 2026-02-13
**Session** : Debug RAG Enhanced - Documents Enrichis
**Durée** : ~3h
**Statut** : ⚠️ Partiellement réussi (53% vs 56% avant)

---

## Contexte

Le système RAG Enhanced avait un **problème fondamental** : il enrichissait la **QUERY** avec des synonymes au lieu d'enrichir les **DOCUMENTS** à l'indexation.

### Approche Initiale (Incorrecte)

```
USER: "allume les lumières"
  ↓ SynonymExpander
QUERY ENRICHIE: "allume active démarre éclaire lumières éclairages lampes"
  ↓ RAG
SCORE DÉGRADÉ: 0.522 (au lieu de 0.568)
  ↓ ConfidenceCascader
FALLBACK (score <0.60) → NO_TOOL
```

**Problème** : L'expansion de la query diluait le signal sémantique et dégradait les scores.

### Approche Corrigée (Implémentée)

```
INDEXATION:
  Document brut: "hue.turn_on_group: Allume un groupe de lumières"
  ↓ Enrichissement
  Document enrichi: "hue.turn_on_group: Allume un groupe de lumières.
                     Utilise pour: allumer un groupe | activer les lumières.
                     Exemples: allume les lumières de la chambre | active l'éclairage"

RECHERCHE:
  USER: "allume les lumières" (query courte, précise)
  ↓ RAG (sans expansion)
  SCORE: ~0.50 (attendu >0.70)
```

---

## Travaux Réalisés

### 1. Création Dictionnaire de Synonymes (`data/synonym_mappings.json`)

**Contenu** :
- 24 actions (allume, éteins, démarre, clone, caste, etc.)
- 18 entités (lumières, télé, vm, ampli, volume, etc.)
- Verbes groupés par catégorie (power, volume, color, list, etc.)

**Format** :
```json
{
  "actions": {
    "allume": ["active", "démarre", "éclaire", "lance", "enclenche"],
    "éteins": ["coupe", "désactive", "ferme", "arrête", "stoppe"]
  },
  "entities": {
    "lumières": ["éclairages", "lampes", "ampoules", "lights"],
    "télé": ["tv", "télévision", "écran", "television"]
  }
}
```

### 2. Modification Script d'Indexation (`scripts/reindex_mcp_rag_optimized.py`)

**Changements majeurs** :
- ✅ Fonction `expand_text_with_synonyms()` : Génère variantes en phrases naturelles
- ✅ Fonction `generate_rich_document()` : Intègre synonymes dans documents
- ✅ Fonction `get_action_variants()` : Variantes du nom d'outil (turn_on → switch_on)

**Exemple de document généré** :
```
hue.turn_on_group (HUE): Turn on all lights in a specific group.
Utilise pour: allumer un groupe de lumières. allumer un pièce de lumières.
              activer les lumières d'une pièce. activer les lampes d'une pièce
Exemples: allume les lumières de la chambre. active les lumières de la chambre.
          allume l'éclairage du salon. active l'éclairage du living
Variantes: switch_on_group | power_on_group | activate_group
Catégorie: hue_control
```

### 3. Désactivation SynonymExpander (`config.yaml`)

```yaml
synonym_expander:
  enabled: false  # DÉSACTIVÉ - Enrichissement côté indexation maintenant
```

### 4. Correction Bug EnhancedPipeline (CRITIQUE)

**Bug trouvé** : EnhancedPipeline utilisait SEULEMENT `_semantic.search()` au lieu de `_retrieve_specs()` qui fait la **RRF Fusion** (semantic + keyword).

**Fix** :
```python
# AVANT (bug)
v2_results = self._pipeline_v2._semantic.search(expanded_query, top_k=5)

# APRÈS (corrigé)
semantic_results = self._pipeline_v2._semantic.search(expanded_query, top_k=10)
v2_results = self._pipeline_v2._retrieve_specs(expanded_query)

# Utiliser ordre RRF (meilleur ranking) + scores semantic (pour cascade)
```

**Raison** : Les scores RRF (0.016-0.033) ne sont PAS comparables aux seuils du ConfidenceCascader (0.60, 0.85).

### 5. Réindexation ChromaDB

```bash
rm -rf .chromadb
python scripts/reindex_mcp_rag_optimized.py
```

**Résultat** : 85 outils indexés avec documents enrichis.

---

## Problèmes Découverts

### 🚨 Problème #1 : Modèle d'Embeddings Inadéquat

**Symptôme** : `hue.turn_on_group` classé **#7** alors qu'il contient littéralement "allume les lumières de la chambre".

**Top 10 pour "allume les lumières de la chambre"** :
```
1. Score: 0.597 - hue.turn_off_light     ← MAUVAIS (turn_OFF au lieu de ON)
2. Score: 0.556 - tv.ambilight_off        ← MAUVAIS
3. Score: 0.528 - hue.turn_off_group      ← MAUVAIS (turn_OFF)
4. Score: 0.481 - tv.ambilight_on
5. Score: 0.477 - tv.ambilight_mode
6. Score: 0.472 - tv.power_off
7. Score: 0.468 - hue.turn_on_group       ← BON OUTIL mais #7 seulement!
8. Score: 0.464 - hue.turn_on_light
```

**Cause** : Le modèle `paraphrase-multilingual-MiniLM-L12-v2` (33M params) **ne distingue PAS bien** les antonymes "allume" vs "éteins".

**Impact** :
- Scores trop bas (<0.70 en général)
- Confusion antonymes (ON/OFF, UP/DOWN)
- turn_OFF score plus haut que turn_ON!

### 🚨 Problème #2 : Scores Globalement Trop Bas

**Résultats tests (15 cas)** :
- ✓ HIGH (>0.85): **0** (0%)
- ✓ MEDIUM (0.60-0.85): **0** (0%)
- ✓ LOW (<0.60): 8 (53%)
- ✗ FAIL: 7 (47%)

**Taux de réussite** : 8/15 (**53%**) vs 10/18 (56%) avant migration

**Conclusion** : L'enrichissement des documents **n'a PAS amélioré** les scores.

### 🚨 Problème #3 : Format Enrichissement Sous-Optimal

**Tentative #1** : Format slash `allume/active/démarre`
- Score: 0.516 (ÉCHEC)
- Les embeddings ne comprennent pas ce format

**Tentative #2** : Phrases naturelles répétées
- Score: 0.468 (ÉCHEC quand même)
- Même avec exemples exacts, scores trop bas

---

## Résultats Finaux

### Tests 15 Cas Critiques

```
✗ [HUE   ] allume les lumières de la chambre  → NO_TOOL             (0.389, FAIL)
✓ [HUE   ] éteins toutes les lumières         → turn_off_group      (0.572, LOW)
✓ [HUE   ] mets les lumières en rouge         → set_group_color_rgb (0.504, LOW)
✓ [HUE   ] baisse la luminosité à 20%         → set_group_brightness(0.504, LOW)
✓ [TV    ] allume la télé                     → tv.power_on         (0.597, LOW)
✓ [TV    ] monte le volume                    → tv.volume_up        (0.430, LOW)
✗ [TV    ] lance YouTube                      → NO_TOOL             (0.658, FAIL)
✓ [VM    ] démarre preprod-09                 → fedora.vm_start     (0.300, LOW)
✓ [VM    ] liste mes VM                       → fedora.vm_status    (0.500, LOW)
✗ [VM    ] clone preprod-09                   → NO_TOOL             (0.362, FAIL)
✗ [VM    ] fais un snapshot                   → NO_TOOL             (0.309, FAIL)
✗ [CAST  ] caste YouTube                      → NO_TOOL             (0.610, FAIL)
✗ [CAST  ] arrête le cast                     → NO_TOOL             (0.369, FAIL)
✓ [DENON ] allume le Denon                    → denon.power_on      (0.476, LOW)
✗ [DENON ] monte le volume de l'ampli         → NO_TOOL             (0.329, FAIL)
```

**Bilan** : 8/15 réussis (53%), **0 scores >0.60**, **PIRE** qu'avant.

---

## Analyses et Conclusions

### ✅ Ce Qui Fonctionne

1. **Fusion RRF** : Combine bien semantic + keyword pour meilleur ranking
2. **Documents enrichis** : Contiennent bien les variantes et exemples
3. **Désactivation SynonymExpander** : Queries restent propres
4. **Architecture** : Séparation indexation/recherche correcte

### ❌ Ce Qui Ne Fonctionne PAS

1. **Modèle d'embeddings trop faible** : 33M params insuffisant
2. **Confusion antonymes** : turn_on vs turn_off, up vs down
3. **Scores jamais >0.70** : Seuils cascade (0.60, 0.85) inatteignables
4. **RRF ne compense pas** : Même avec fusion, scores restent bas

### 🎯 Cause Racine

Le **modèle d'embeddings `paraphrase-multilingual-MiniLM-L12-v2`** est le goulot d'étranglement :
- Trop petit (33M params)
- Embeddings trop proches pour antonymes
- Pas assez de granularité sémantique

**Preuve** : Document contenant littéralement "allume les lumières de la chambre" classé #7 avec score 0.468.

---

## Solutions Possibles

### Option A : Changer de Modèle d'Embeddings (RECOMMANDÉ)

**Modèles suggérés** :

1. **`paraphrase-multilingual-mpnet-base-v2`** (279M params)
   - ✅ Meilleur modèle multilingue (SOTA)
   - ✅ Scores attendus: +0.20 à +0.30
   - ❌ Plus lent (~500ms vs ~100ms)
   - ❌ Plus de VRAM (~2GB vs ~500MB)

2. **`sentence-transformers/LaBSE`** (471M params)
   - ✅ Excellent pour multilingue
   - ✅ Scores très précis
   - ❌ Très lent (~800ms)
   - ❌ Beaucoup de VRAM (~3GB)

3. **`distiluse-base-multilingual-cased-v2`** (135M params)
   - ✅ Compromise taille/performance
   - ✅ Meilleur que MiniLM
   - ⚠️ Moins bon que mpnet

**Implémentation** :
```yaml
# config.yaml
rag:
  chromadb:
    embedding_model: "paraphrase-multilingual-mpnet-base-v2"  # Changement
```

**Effort** : 10 min (changer config + réindexer)
**Impact attendu** : +30% taux réussite (de 53% → 75-80%)

### Option B : Baisser les Seuils du ConfidenceCascader

**Changement** :
```yaml
# config.yaml
rag_enhanced:
  feedback_loop:
    confidence_high: 0.70  # Au lieu de 0.85
    confidence_low: 0.45   # Au lieu de 0.60
```

**Impact** : Plus de tools générés, mais plus de faux positifs
**Effort** : 2 min
**Recommandation** : **NON**, masque le problème sans le résoudre

### Option C : Boosting Keyword (BM25) dans Fusion

**Augmenter le poids du keyword retriever** :
```python
# Dans fusion.py, modifier le calcul RRF
keyword_weight = 2.0  # Doubler le poids du keyword
rrf_score = (semantic_score / (k + rank)) + (keyword_score * keyword_weight / (k + rank))
```

**Impact** : BM25 ne souffre pas du problème antonymes
**Effort** : 30 min
**Recommandation** : **PEUT AIDER** en combinaison avec Option A

### Option D : Fine-tuning Custom du Modèle

**Approche** : Fine-tuner le modèle sur corpus MCP/domotique français

**Effort** : 40-80h (collecte data, training, validation)
**Recommandation** : **NON**, trop coûteux pour le bénéfice

---

## Recommandation Finale

### 🎯 Solution à Court Terme (1h)

1. **Changer pour `paraphrase-multilingual-mpnet-base-v2`**
   - Modifier `config.yaml`
   - Réindexer ChromaDB
   - Re-tester
   - **Impact attendu** : 75-80% réussite, 20-30% scores HIGH

2. **Si VRAM insuffisant** : Utiliser `distiluse-base-multilingual-cased-v2`

3. **Optionnel** : Booster keyword dans fusion (×1.5 ou ×2)

### 📊 Résultats Attendus Après Migration

| Métrique | Actuel | Après mpnet |
|----------|--------|-------------|
| Taux réussite | 53% | **75-80%** |
| Scores HIGH (>0.85) | 0% | **20-30%** |
| Scores MEDIUM | 0% | **40-50%** |
| Score moyen | 0.45 | **0.70** |

### ⏭️ Next Steps

1. **Approuver** le changement de modèle d'embeddings
2. **Tester** avec mpnet-base-v2
3. **Valider** amélioration des scores (objectif: >75% réussite)
4. **Ajuster** seuils cascade si nécessaire
5. **Documenter** résultats finaux

---

## Fichiers Modifiés

| Fichier | Statut | Description |
|---------|--------|-------------|
| `data/synonym_mappings.json` | ✅ Créé | Dictionnaire 24 actions + 18 entités |
| `scripts/reindex_mcp_rag_optimized.py` | ✅ Modifié | Enrichissement documents |
| `config.yaml` | ✅ Modifié | SynonymExpander disabled |
| `lyra/rag_enhanced/pipeline_enhanced.py` | ✅ Corrigé | RRF Fusion + scores semantic |
| `.chromadb/` | ✅ Réindexé | 85 outils enrichis |

---

## Bugs Corrigés

1. ✅ **EnhancedPipeline utilisait seulement semantic** au lieu de RRF fusion
2. ✅ **Scores RRF (0.016) incompatibles** avec seuils cascade (0.60, 0.85)
3. ✅ **SynonymExpander dégradait scores** (désactivé)
4. ✅ **Documents pas enrichis** (maintenant enrichis avec variantes)

---

## Limites Identifiées

1. ❌ **Modèle d'embeddings trop faible** pour distinguer antonymes
2. ❌ **Scores jamais >0.70** avec modèle actuel
3. ❌ **Enrichissement documents ne suffit pas** si embeddings faibles
4. ⚠️ **VRAM contrainte** (RTX 3080 Ti 12GB) pour gros modèles

---

## Conclusion

L'approche "enrichissement côté indexation" est **théoriquement correcte** mais **limitée par le modèle d'embeddings**.

**Verdict** : Migration partiellement réussie (architecture OK) mais **performances insuffisantes** (53% réussite).

**Action requise** : **Changer de modèle d'embeddings** pour débloquer le système.

**ETA solution complète** : 1h (changement modèle + réindexation + tests)
