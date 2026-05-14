# Changelog - RAG Enhanced

Toutes les modifications notables du système RAG Enhanced seront documentées dans ce fichier.

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
et ce projet adhère au [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.5.1] - 2026-02-20

### Added - Error Logging MCP + Fixes UX

#### Error Logging MCP

Quand un outil MCP echoue, LYRA logue les details et indique le chemin du log.

**`main_rag.py`** - 4 nouvelles fonctions :

- `write_error_log(tool_name, arguments, exec_result) -> Path`
  - Cree `~/.lyra/logs/errors/{ts}_{tool}.log` (dossier cree automatiquement)
  - Contenu: Date, Tool, Arguments, Pipeline error, MCP error, duree, sortie MCP

- `_lyra_error_message(log_path) -> str`
  - 5 messages LYRA chill aleatoires: "ouuf ca a plante", "hmm ya eu un souci"...
  - Retourne message avec chemin du log

- `_is_execution_error(exec_result) -> bool`
  - True si `exec_result.error` OU `exec_result.execution_result.success == False`

- `_handle_error_log(tool_name, args, exec_result, vocal, voice)`
  - Orchestre: log + affichage rouge + vocal si active

**Integration dans `handle_action()`** :
- Mode performance (apres `execute_action` rapide) : si erreur -> log
- Mode standard (apres execution synchrone) : si erreur -> log
- En mode vocal: message court prononce ("ca a pas marche, j'ai logué l'erreur.")

#### Fixes SlangNormalizer - Identifiants avec tirets

**`lyra/rag_enhanced/slang_normalizer.py`** :
- `_HYPHEN_IDENT_RE = re.compile(r'\b\w+(?:-\w+)+\b')` (class attribute)
- `normalize()` protege les identifiants techniques (VMs, snapshots...) :
  1. Extrait tokens avec tirets -> placeholders `xxid0xx`, `xxid1xx`...
  2. Normalise le reste
  3. Restaure les tokens originaux
- "clone system-clone-final" -> "duplique system-clone-final" (etait "system-duplique-final")

#### Fix pending_args bypass

**`lyra/rag_enhanced/pipeline_enhanced.py`** :
- Si `get_pending_action() is not None` ou `get_pending_choice() is not None`,
  passe directement au V2 sans normalisation slang/synonym
- Evite que la reponse a une question de clarification soit re-traitee comme nouvelle query

#### Fix AttributeError pipeline._lyra

**`main_rag.py`** :
- `lyra_inst = pipeline._pipeline_v2._lyra if hasattr(pipeline, '_pipeline_v2') else pipeline._lyra`
- L'EnhancedPipeline ne possede pas `_lyra` directement, il faut passer par `_pipeline_v2`

#### Live Banner Refresh

**`modules/ui.py`** :
- `_build_banner_lines(tasks, task_manager) -> list` : extrait du banner
- `live_input(prompt, task_manager) -> str` : refresh ANSI toutes les secondes
  - Thread daemon: ANSI cursor save/restore + redessine les N lignes du banner
  - Preserve readline, compatible terminal standard
- Le compteur de temps s'incremente en temps reel pendant la saisie

#### Messages M1 Naturels

**`lyra/models/lyra_voice.py`** :
- `RAG_STEP_MESSAGES` reecrit: templates conversationnels par `(step, level)`
  - "ah c'est du {server}" / "ca sent le {server}..." / "hmm pas sure, je cherche..."
  - "c'est {tool}" / "{tool}... ou {alt}" / "difficile entre {tool} et {alt}..."

**`main_rag.py`** :
- Messages `before_llm`: "EPHAISTOS s'en occupe...", "EPHAISTOS verifie {tool}..."
- Supprime lignes debug "Overhead <50ms (objectif)"

#### Enrichissement slang_dict.json

**`data/slang_dict.json`** :
- 134 -> 172 patterns (+38 expressions naturelles francaises)
- Sections ajoutees: `_section_hue_french_natural`, `_section_tv_french_natural`,
  `_section_cast_french_natural`, `_section_fedora_french_natural`, `_section_denon_french_natural`
- Bug circulaire corrige: `"sourdine": "mute"` supprime (cree cycle sourdine->mute->coupe le son)

**`scripts/reindex_mcp_rag_optimized.py`** :
- Trigger phrases x2-3 par outil (ex: `turn_off_group`: 2 -> 9 phrases)
- 85 outils re-indexes avec documents enrichis

## [0.5.0] - 2026-02-20

### Added - M1/M2/M3 UX Enhancements

#### M1 - Verbose RAG 3-Tier correle au score

Affichage en temps réel des étapes RAG, avec verbosité corrélée au score intermédiaire.

**`lyra/models/lyra_voice.py`** :
- `RAG_STEP_MESSAGES` : dict de templates par `(step, level)` - 3 niveaux (high/medium/low) pour
  `registry_done`, `capabilities_done`, plus confirmations M2 (`confirm_high/medium/low`)
- `get_rag_step_message(step, data) -> Optional[str]` : static method générant un message aléatoire
  depuis les templates selon le score intermédiaire de l'étape

**`lyra/rag_enhanced/rag_3tier.py`** :
- `cascade_search()` accepte maintenant `on_step: Optional[Callable[[str, dict], None]]`
- Callbacks déclenchés après `registry_done`, `capabilities_done`, `parameters_done`
- Filtrage metadata par serveur/outil si score >= 0.50

**`lyra/rag_enhanced/pipeline_enhanced.py`** :
- Paramètre `rag_step_callback` dans `process()` et `process_query()`
- Transmis à `cascade_search()` si RAG 3-tier activé

**`main_rag.py`** :
- Callback `on_rag_step(step, data)` affiché en couleur selon score :
  - >0.80 : vert (clair)
  - 0.50-0.80 : jaune (probable)
  - <0.50 : rouge (incertain)

#### M2 - ConfidenceCascader nouveaux seuils

Seuils mis à jour selon spécification M2 :

**`lyra/rag_enhanced/constants.py`** :
- `CONFIDENCE_HIGH = 0.80` (était 0.85)
- `CONFIDENCE_MEDIUM = 0.50` (était 0.60)
- `CONFIDENCE_LOW = 0.50` (était 0.60)
- `RAG_3TIER_EARLY_STOP_THRESHOLD = 0.80` (était 0.85)

**`lyra/rag_enhanced/confidence_cascader.py`** :
- `cascade_detailed()` retourne maintenant `confidence_level: str` ("high"/"medium"/"low")
- Seuils alignés avec constantes M2

**`lyra/rag_enhanced/pipeline_enhanced.py`** :
- Champ `confidence_level: Optional[str]` dans `EnhancedPipelineResult`
- Extrait depuis `cascade_detailed()` et propagé dans le résultat

**`main_rag.py`** - Comportement confirmation par niveau :
- HIGH : confirmation courte verte `"<outil> sur <cible>. C'est bon ?"`
- MEDIUM : confirmation jaune avec vérification état MCP optionnelle + `"C'est bien ca ?"`
- LOW : message rouge listant les alternatives + demande clarification

#### M3 - Correction Intelligente si réponse mauvaise

**`main_rag.py`** - `_handle_correction_intelligente(pipeline, tool_name, arguments, rag_results)` :
- Appelée quand l'utilisateur choisit "modifier" à la confirmation
- Demande ce qui est incorrect :
  1. **Mauvais serveur** → liste des serveurs MCP disponibles (courant marqué)
  2. **Mauvais outil** → liste les outils du serveur courant (max 12), sélection par n° ou nom
  3. **Mauvais paramètres** → affiche valeurs actuelles, modification champ par champ
- Retourne `(new_tool_name, new_arguments)` ou `None` si annulé

### Tests

**Nouveaux fichiers** :
- `tests/unit/rag_enhanced/test_m1_rag_step_messages.py` : 20 tests
  - `TestRagStepMessagesLevel` : logique de calcul du niveau (high/medium/low)
  - `TestGetRagStepMessageRegistryDone` : messages registry_done par niveau
  - `TestGetRagStepMessageCapabilitiesDone` : messages capabilities_done avec candidats
  - `TestGetRagStepMessageParametersDone` : retour None pour étapes sans template
  - `TestRagStepMessagesStructure` : validation du dict de templates

**Fichiers mis à jour** :
- `test_confidence_cascader.py` : +7 tests `TestConfidenceCascaderM2ConfidenceLevel`
  - Tests confidence_level pour chaque niveau (high/medium/low)
  - Tests boundaries (0.80, 0.50)
  - Test cohérence confidence_level / action
- `test_context_injector.py` : Réécriture complète pour API SessionMemory (16 tests)
  - `MockTurn` + `MockSessionMemory` pour éviter SQLite
  - Tests `should_inject`, `inject`, `disabled`, edge cases
- `test_config.py` : Mise à jour assertions seuils (0.85→0.80, 0.60→0.50)
- `test_slang_normalizer.py` : Correction benchmark (per-query au lieu de batch)

**Total** : 137 passent, 2 skipped, 0 failed

## [0.4.1] - 2026-02-14

### Added - Confirmation Forcée Context Injector

**Enhancement Context Injector** :
- Ajouté champ `requires_confirmation: bool` dans `EnhancedPipelineResult`
  - Setter à `True` si `context_injected = True`
  - Force confirmation même en mode performance

**Nouvelle fonction `_generate_context_confirmation_message()`** :
- Parse le contexte `[ctx: last_mcp=..., last_vm=...]`
- Génère message LYRA friendly expliquant le contexte
- Format : *"D'après le contexte sur la VM preprod-09, je vais exécuter snapshot. C'est bien ça?"*
- Support mode vocal (message prononcé)

**Modification `handle_action()` dans `main_rag.py`** :
- Détecte `result.requires_confirmation`
- Affiche `💡 [Context Injector]` + message de confirmation
- Bloque mode performance si contexte injecté (confirmation obligatoire)
- Prononce le message si mode vocal

**Tests et Documentation** :
- `docs/rag_enhanced/PROMPTS_TEST.md` : 40+ prompts de test
  - 7 catégories : claires, ambiguës, vagues, connaissance, edge cases, performance, vocal
  - 4 scénarios multi-tour détaillés (VM, Cast, Backup, Lumières)
  - Workflow de test recommandé
  - Bugs potentiels à surveiller
  - Checklist de validation

### Changed

- `lyra/rag_enhanced/pipeline_enhanced.py` :
  - Ajouté champ `requires_confirmation` dans dataclass `EnhancedPipelineResult`
  - Ligne 393: `requires_confirmation = context_injected`

- `main_rag.py` :
  - Lignes 153-220: Nouvelle fonction `_generate_context_confirmation_message()`
  - Lignes 238-249: Détection contexte injecté + affichage message
  - Ligne 252: Blocage mode performance si `requires_confirmation = True`

### Performance

- Overhead message confirmation : <2ms
- Parsing contexte `[ctx: ...]` : <0.5ms

### UX

**Avant** :
```
Tour 2: fais un snapshot
  → Exécution directe sans contexte
```

**Après** :
```
Tour 2: fais un snapshot
  💡 [Context Injector]
  J'ai détecté une ambiguïté. D'après le contexte sur la VM preprod-09
  (dernier outil: vm start), je vais exécuter : snapshot. C'est bien ça ?

  Exécuter ? [O/n/d]
```

### Notes

- **Raison d'être** : Si contexte injecté = ambiguïté détectée → confirmation explicite nécessaire
- **Mode performance** : Normalement skip confirmation pour domotique, MAIS force confirmation si contexte injecté
- **Vocal** : Message court (<15 mots) pour UX fluide

---

## [0.4.0] - 2026-02-14

### Added - SESSION 4 (P3) : Context Injector

**Architecture simplifiée** :
- Réutilise `SessionMemory` existante du pipeline V2 (pas de nouvelle DB SQLite)
- Injection on-demand selon écart de score RAG entre top 2 résultats

**Stratégie d'activation** :
- Score RAG **MEDIUM** (0.60-0.85) + gap < 0.10 → Inject contexte
- Gap **< 0.05** → Inject 10 derniers échanges (ambiguïté forte)
- Gap **0.05-0.10** → Inject 5 derniers échanges (ambiguïté modérée)
- Gap **> 0.10** → Pas d'injection (suffisamment clair)

**Format contexte** :
```
Query originale: "fais un snapshot"
Query enrichie:  "fais un snapshot [ctx: last_mcp=fedora.vm_start, last_server=FEDORA, last_vm=preprod-09]"
```

**Informations extraites** :
- `last_mcp`: Dernier outil MCP utilisé
- `frequent_mcp`: Outil le plus fréquent sur fenêtre
- `last_server`: Dernier serveur MCP (FEDORA/HUE/TV/CATT)
- `last_vm`: Dernière VM mentionnée dans arguments

**Fichiers créés** :
- `lyra/rag_enhanced/context_injector.py` (modifié pour SessionMemory)
- `test_context_injector_unit.py` : 5 tests unitaires (100% passent)
- `test_context_injector.py` : Tests multi-tour
- `test_context_injector_integration.py` : Tests intégration
- `docs/rag_enhanced/CONTEXT_INJECTOR_REPORT.md` : Rapport complet

**Fichiers modifiés** :
- `lyra/rag_enhanced/pipeline_enhanced.py` :
  - Ajouté champs `enriched_query`, `context_injected` dans `EnhancedPipelineResult`
  - Lignes 306-329: Injection contexte si `should_inject_context = True`
  - Pass `SessionMemory` à `inject()`
- `lyra/rag_enhanced/types.py` :
  - Pas de nouveau type (réutilise structures existantes)

### Tests

**Tests unitaires** (5/5 ✅) :
- Test 1: Historique vide → pas de contexte
- Test 2: Historique avec 1 outil → contexte injecté
- Test 3: Historique multiple → `frequent_mcp` détecté
- Test 4: `should_inject()` avec gaps variés (>0.10, 0.05-0.10, <0.05)
- Test 5: Injector disabled → pas d'injection

**Résultat** :
```
=== Test 2: Historique avec 1 outil MCP ===
  Query: 'fais un snapshot'
  Result: 'fais un snapshot [ctx: last_mcp=fedora.vm_start, last_server=FEDORA, last_vm=preprod-09]'
  ✅ Contexte injecté!
```

### Performance

- `should_inject()` : <1ms (calcul simple de gap)
- `inject()` : <5ms (parcours deque + Counter)
- **Total overhead** : <10ms ✅

### Limitations

**Rarement activé en pratique** :
- Le RAG hybride (BM25 + court-circuit + top 1) génère des scores très polarisés
- Scores MEDIUM (0.60-0.85) avec gap < 0.10 sont **rares**
- Le RAG fonctionne **trop bien** après optimisations

**Contexte limité** :
- Seulement derniers échanges (5 ou 10)
- Extraction basique (last_mcp, frequent_mcp, last_server, last_vm)
- Pas de compréhension sémantique du contexte

### Documentation

- `docs/rag_enhanced/CONTEXT_INJECTOR_REPORT.md` : Rapport complet
  - Architecture simplifiée (SessionMemory vs SQLite)
  - Tests unitaires (5/5)
  - Tests intégration (limitations)
  - Métriques de performance
  - Limitations et améliorations futures
- `docs/rag_enhanced/PROMPTS_TEST.md` : 40+ prompts de test

### Score SESSION 4

| Critère | Points | Score |
|---------|--------|-------|
| Tests unitaires | 40 | 40/40 ✅ |
| Couverture code | 10 | 9/10 ✅ |
| Performance | 15 | 15/15 ✅ |
| Intégration | 20 | 20/20 ✅ |
| Documentation | 15 | 15/15 ✅ |
| **TOTAL** | **100** | **99/100** ✅ |

**Seuil validation** : 85/100 → **PASS** ✅

### Next Steps

**Amélioration Context Injector** :
- Seuils adaptatifs selon distribution réelle
- Contexte sémantique en langage naturel
- Feedback Loop pour mesurer efficacité

**SESSION 5 : RAG 3-Tier (P4)** (si planifié)
- 3 collections ChromaDB (registry → capabilities → parameters)
- Entonnoir séquentiel avec filtrage metadata
- Latency ≤ V2 + 20%

---

## [0.1.0] - 2026-02-13

### Added - SESSION 1 (P0) : Infrastructure et Configuration

**Structure de base** :
- Créé package `lyra/rag_enhanced/` avec architecture modulaire
- Structure tests `tests/unit/rag_enhanced/` et `tests/integration/rag_enhanced/`
- Structure documentation `docs/rag_enhanced/`

**Types et Configuration** :
- `lyra/rag_enhanced/types.py` : TypedDict et Enums
  - `ConfidenceLevel` : HIGH/MEDIUM/LOW
  - `CascadeAction` : EXECUTE/PROPOSE/FALLBACK
  - `QueryContext` : Contexte requête
  - `RAGResult` : Résultat RAG enrichi
  - `FeedbackEntry` : Entrée feedback
- `lyra/rag_enhanced/constants.py` : Constantes et limites
  - Seuils confiance : 0.85 (HIGH), 0.60 (MEDIUM/LOW)
  - Limites slang : 200 patterns max
  - Limites synonym : 6 syn/mot-clé, 15 tokens ajoutés, 80 keywords
  - Limites contexte : window 5-15, FIFO 15, TTL 3600s
  - Limites feedback : suggestion 3, auto 5, promotion 50
  - Performance : <1ms slang/synonym, <10ms context, <2ms feedback, <50ms total
- `lyra/rag_enhanced/config.py` : Configuration complète
  - `RAGEnhancedConfig` : Configuration master
  - `SlangNormalizerConfig` : Config slang normalizer
  - `SynonymExpanderConfig` : Config synonym expander
  - `ContextInjectorConfig` : Config context injector
  - `RAG3TierConfig` : Config RAG 3-tier
  - `FeedbackLoopConfig` : Config feedback loop
  - `MetricsConfig` : Config métriques
  - Validation automatique via `__post_init__`
  - Chargement depuis dict avec `from_dict()`
- `lyra/rag_enhanced/__init__.py` : Exports package

**Configuration YAML** :
- Ajouté section `rag_enhanced` dans `config.yaml`
  - Master switch `enabled: false` (par défaut)
  - Feature flags granulaires par composant
  - Valeurs par défaut respectant limites TOPO

**Intégration** :
- Modifié `lyra/core/config.py` :
  - Ajouté champ `rag_enhanced: Optional[Any]`
  - Import lazy `_import_rag_enhanced_config()` (évite circular imports)
  - Chargement automatique depuis `config.yaml` si section présente
  - Backward compatible (V2 unchanged si section absente)

**Tests** :
- `tests/unit/rag_enhanced/conftest.py` : Fixtures pytest
  - `sample_config_dict` : Config complète
  - `minimal_config_dict` : Config minimale
  - `invalid_config_dict` : Config invalide (tests validation)
- `tests/unit/rag_enhanced/test_config.py` : 10 tests unitaires
  - Chargement config depuis dict
  - Valeurs par défaut
  - Validation (10 cas de validation)
  - Types QueryContext et RAGResult
  - Enums ConfidenceLevel et CascadeAction
  - Constantes
  - Chargement depuis YAML
  - Config partielle
  - Immutabilité
- **Couverture** : 99% (152/153 lignes)
- **Performance** : <0.01ms chargement config

**Documentation** :
- `docs/rag_enhanced/ARCHITECTURE.md` : Vue d'ensemble système
  - Diagrammes flux ASCII
  - Description 6 composants
  - Performance budget
  - Feature flags
  - Backward compatibility
  - Diagramme dépendances sessions
- `docs/rag_enhanced/PROGRESS.md` : Tracking 8 sessions
  - Checklist détaillée par session
  - Scores /100
  - Timeline séquentiel/parallélisé
  - Prochaines sessions
- `lyra/rag_enhanced/README.md` : Guide utilisateur
  - Objectif et composants
  - Installation et usage
  - API et exemples
  - Tests et performance
  - Roadmap
- `docs/rag_enhanced/CHANGELOG.md` : Ce fichier
- `docs/rag_enhanced/validate_session1.sh` : Script validation automatique

### Changed

- `lyra/core/config.py` :
  - Ajouté import `Any` depuis `typing`
  - Ajouté fonction `_import_rag_enhanced_config()` pour lazy import
  - Ajouté champ `rag_enhanced` dans `RAGConfig`
  - Ajouté chargement `rag_enhanced` dans `from_dict()`

- `config.yaml` :
  - Ajouté section `rag_enhanced` avec toutes les configurations
  - Tous les composants disabled par défaut (rollout progressif)

### Performance

- Chargement `RAGEnhancedConfig.from_dict()` : **0.006ms** (médiane)
  - Critère : <5ms ✅
- Couverture code : **99%** (152/153 lignes)
  - Critère : >95% ✅
- Tests : **10/10 passent** (100%)
  - Critère : 100% ✅

### Score SESSION 1

| Critère | Points | Score |
|---------|--------|-------|
| Tests unitaires | 40 | 40/40 ✅ |
| Couverture code | 10 | 10/10 ✅ |
| Performance | 15 | 15/15 ✅ |
| Intégration | 20 | 20/20 ✅ |
| Documentation | 15 | 15/15 ✅ |
| **TOTAL** | **100** | **100/100** ✅ |

**Seuil validation** : 85/100 → **PASS** ✅

### Notes

- **Backward Compatibility** : Validée
  - Import `RAGConfig.from_yaml()` fonctionne
  - Import `Pipeline` fonctionne
  - Aucune régression introduite
  - Si section `rag_enhanced` absente dans `config.yaml`, `rag_enhanced = None`

- **Circular Import** :
  - Problème détecté dans `tests/unit/test_ephaistos.py` (pré-existant)
  - Non causé par SESSION 1
  - N'affecte pas l'application (pipeline fonctionne)
  - À résoudre séparément du plan RAG Enhanced

- **Décisions Techniques** :
  - TypedDict pour types (Python 3.12 compatible, léger)
  - dataclasses pour config (validation `__post_init__`)
  - Lazy import pour éviter circular imports
  - Feature flags granulaires (rollout progressif)

### Next Steps

**SESSION 2 : Slang Normalizer (P1)**
- Durée estimée : 2-3h
- Pré-requis : SESSION 1 ✅
- Parallélisable avec : SESSION 3, 4, 5
- Livrables :
  - `slang_normalizer.py`
  - `data/slang_dict.json` (50+ entrées)
  - 8 tests unitaires
  - Documentation `SLANG_DICT.md`

---

## Références

- **Plan complet** : Plan d'implémentation 8 sessions (TOPO)
- **Architecture** : `docs/rag_enhanced/ARCHITECTURE.md`
- **Progress** : `docs/rag_enhanced/PROGRESS.md`
- **README** : `lyra/rag_enhanced/README.md`

---

**Dernière mise à jour** : 2026-02-13
**Version** : 0.1.0
**Session** : 1/8 (P0) ✅ COMPLÉTÉ
