# Changelog - Lyra

## [v1.1.0 - Pipeline modulaire complet] - 2026-03-10

### Refactoring - Decomposition de pipeline.py en modules separes (7 missions)

`pipeline.py` passe de 2899 lignes a 919 lignes (~68% de reduction).
164/164 tests MCP conserves a 100% apres chaque mission.

**Mission 1 - Types et constantes (`core/types.py`, `core/config.py`)**
- Extraction de `QueryType`, `PipelineResult`, constantes MCP (`CATEGORY_KEYWORDS`, `TOOL_TYPE_KEYWORDS`, etc.)

**Mission 2 - Retrievers (`core/retrieval.py`)**
- Classe `Retriever` : encapsule SemanticRetriever + KeywordRetriever + RRFFusion
- API : `initialize()`, `retrieve(query)`, `detect_query_type(query)`
- Pipeline utilise `self._retriever` au lieu de 3 composants separes

**Mission 3 - Menus outils (`core/menus.py`)**
- `is_list_tools_query()`, `process_tools_query_step1()`, `handle_server_selection()`
- Constantes `LIST_VERBS`, `LIST_SUBJECTS`

**Mission 4 - Workflows base (`core/workflows/`)**
- `context.py` : `WorkflowContext` avec callables injectes (`prepare_execution`, `route_query`)
- `vm_start.py` : `handle_vm_start_confirm()` (4 cas oui/non/clarification/autre)
- `vm_stop.py` : `handle_vm_stop_choice()` (choix 1/2/3 arret VM avant clone)
- `vm_snapshot.py` : `handle_vm_snapshot_create_workflow()`, `handle_vm_snapshot_list_workflow()`, `handle_vm_snapshot_pending()`

**Mission 5 - Workflows clone/export (`core/workflows/vm_clone.py`, `vm_export.py`)**
- `vm_clone.py` : `suggest_vm_name()`, `handle_cow_choice()`, `handle_vm_clone_workflow()` (6 cas validation)
- `vm_export.py` : `CUSTOM_EXPORT_GROUPS`, workflow multi-tours (6 groupes virt-sysprep + firstboot)

**Mission 6 - Formatters et validation (`core/formatters.py`, `core/validation.py`)**
- `formatters.py` : `enrich_description()`, `enrich_optional_args()`, `format_listing_result()`
- `validation.py` : `validate_vm_existence()`, helpers VM state, constantes outils VM

**Mission 7 - Cleanup final**
- Suppression imports inutilises (`re`, `sys`, `unicodedata`) dans pipeline.py
- Mise a jour CLAUDE.md section "Project Structure"
- 164/164 PASS confirme (100%)

---

## [v0.7 - 53/54 Tests MCP] - 2026-02-25

### Campagne de tests complete - 54 tests MCP one-shot

Passage de 38/54 (70%) a 53/54 (98%). Un seul FAIL attendu (T10: vm_clone, source VM inexistante).

**Fixes FEDORA:**
- T1: vm_status({}) pour listing global (etait vm_name='' -> EXEC_ERROR)
- T6: vm_exec(vm_name, cmd) "execute CMD sur VM" (etait ls() mauvais outil)
- T7: vm_copy(source, vm_name, dest) "copie FILE vers VM" (etait FAIL)
- T11: vm_clone_system(name) "clone systeme VM en NEWVM" (etait FAIL)
- T12: vm_verify(vm_name) "verifie la VM NAME" (etait FAIL)
- T14: backup_status({}) sans watch=True (etait TIMEOUT boucle infinie)
- T15: backup_create(vm_name) args corrects (etait sans vm_name)
- T16: backup_verify(vm_name) argument correct (etait type= au lieu de vm_name=)

**Fixes TV:**
- T30: tv.volume_up (etait tv.power_on)
- T31: tv.volume_down (etait FAIL)
- T33: tv.mute (etait tv.power_off)

**Fixes DENON:**
- T39: denon.power_off (etait eteins() mauvais outil)
- T42: denon.volume_set(level=50) (etait hue.set_brightness mauvais outil!)
- T44: denon.mute_off (etait denon(status=off))

**Fixes HUE:**
- T19: hue.turn_on_group(group_id=81) (etait allume() via embedding ChromaDB confus)
- T27: hue.turn_off_light (etait turn_on_light!)

**Fixes CATT:**
- T46: catt.cast_scan (etait catt.cast_dual_stop)
- T51: catt.cast_volume (etait denon.volume_up + intent=knowledge)

**Changements techniques:**

1. **BM25 accent normalization** (`keyword_retriever.py`):
   - `_tokenize()` normalise les accents (NFD) avant BM25
   - "Demarre" dans docs ChromaDB = "demarre" dans query sans accent

2. **`_rule_based_detect()` etendue** (`pipeline.py`):
   - BACKUP (6 regles): backup_status/list/verify/create/restore/clean
   - FEDORA VM (9 regles): vm_start/stop/destroy/exec/snapshot/status/verify/copy/clone_system
   - CATT (2 regles): cast_scan, cast_volume (avec support "diffuse" = SlangNorm("cast"))
   - HUE (2 regles): turn_on_group, turn_off_light
   - vm_start: exclusion TV context ("lance Netflix sur la TV" -> PAS vm_start)

3. **`_DEMANDE_VERBS_RE` etendu** (`intent_classifier.py`):
   - Ajoute: status|statut|nettoie|restaure|allume|eteins|mute|scan|caste|lance|demarre|arrete|supprime

4. **FRENCH_ENRICHMENTS** (`pipeline.py`):
   - turn_on_group/turn_off_group: retire verbes dupliques (deja fournis par "turn_on"/"turn_off")
   - Distingue singular ("lumiere") vs pluriel ("lumieres") pour light vs group

5. **Normalisation accents dans `_rule_based_detect()`**:
   - NFD normalization au debut (SlangNorm ajoute des accents: "execute"->"exécute")

**Fichiers modifies:**
- `lyra/rag/keyword_retriever.py`: `_tokenize()` accent normalization
- `lyra/models/intent_classifier.py`: `_DEMANDE_VERBS_RE` etendu
- `lyra/core/pipeline.py`: `_rule_based_detect()`, FRENCH_ENRICHMENTS, vm_start TV exclusion

---

## [v0.6.1 - Fixes RAG TV/DENON/CATT] - 2026-02-25

### Fixes RAG TV/DENON/CATT (pipeline.py)

**Cause racine:** EPHAISTOS 0.5b echoue sur les outils domotique (volume TV, mute, Denon).
BM25 retourne de mauvais outils ("volume denon a 50" → catt.cast_volume, "demute le denon" → denon.power_off).
SlangNormalizer transforme "cast" → "diffuse" ce qui casse la detection cast_scan.

**Fix: regles TV/DENON/CATT dans `_rule_based_detect()`** (`pipeline.py`):
- TV: `tv.volume_up/down/set/mute` detectes par presence de "tv/tele" + verbe/chiffre/sourdine
- DENON: `denon.power_on/off/mute_on/off/volume_up/down/set` detectes par presence de "denon"
  - Couvre formes original ("eteins", "demute") et normalisees ("sourdine")
  - Ordre: power_off/on → mute_off/on → volume_set → volume_up/down
- CATT scan: "scan + cast/diffuse/appareils" → `catt.cast_scan`
  (gere les deux formes: original "cast" et SlangNorm "diffuse")

**Resultats:**

| Query | Avant | Apres |
|-------|-------|-------|
| "monte le volume de la TV" | EPHAISTOS 0.5b echec | tv.volume_up OK |
| "coupe le son de la TV" | EPHAISTOS 0.5b echec | tv.mute OK |
| "volume denon a 50" | BM25 → catt.cast_volume | denon.volume_set {level:50} OK |
| "demute le denon" | BM25 → denon.power_off | denon.mute_off OK |
| "eteins le denon" | BM25 score trop bas | denon.power_off OK |
| "scan les appareils cast" | SlangNorm → cast_youtube | catt.cast_scan OK |

**Fichiers modifies:**
- `lyra/core/pipeline.py` : `_rule_based_detect()` etendu avec regles TV/DENON/CATT

---

## [v0.6 - One-Shot + Fixes RAG] - 2026-02-25

### Mode One-Shot CLI

Ajout du mode one-shot: `lyra "[requete]" [-v] [-y]`

- `lyra "demarre preprod-01"` - execution directe sans UI interactive
- `-v / --verbose` : affiche les etapes RAG en temps reel (`[rag]`, `[intent]`, `[action]`)
- `-y / --yes` : auto-confirme les actions (mode non interactif)
- Codes de sortie: 0=OK, 1=EXEC_ERROR, 2=CANCEL, 3=PIPELINE_FAIL, 124=TIMEOUT

**Fichiers modifies:**
- `main_rag.py` : fonction `run_one_shot()`, argparse mis a jour
- `run.sh` : documentation one-shot dans les commentaires

### Tests MCP one-shot (54 tests)

Resultats: 38/54 = 70% (voir `test_mcp_results.md`)

| Serveur | Total | OK | Problemes |
|---------|-------|----|-----------|
| FEDORA | 18 | 11 | 7 |
| HUE | 9 | 8 | 1 |
| TV | 9 | 5 | 4 |
| DENON | 9 | 6 | 3 |
| CATT | 8 | 7 | 1 |
| MERMAID | 1 | 1 | 0 |

### Fixes RAG FEDORA (vm_clone_system, vm_clone, vm_copy, vm_verify)

**Cause racine identifiee:** EPHAISTOS 0.5b trop petit pour extraire les arguments, enrichissements BM25 confondent "copie" avec vm_clone, IntentClassifier classe "verifie" comme "info".

**Fix 1 - vm_clone_system** (`pipeline.py`):
- Bug substring: `"vm_clone" in "fedora.vm_clone_system"` = True
- Fix: `analysis.tool in ("vm_clone", "fedora.vm_clone")`

**Fix 2 - vm_clone** (`pipeline.py`):
- EPHAISTOS detecte l'outil mais `arguments={}` + `missing_args=[]` → NullPointerError ligne 1290
- Fix: regex fallback dans `_handle_vm_clone_workflow` extrait "clone X en Y"
- Fix: null-check `if source_vm and vm.replace(...)`
- Fix: `_rule_based_detect()` intercepte "clone X en Y" avant EPHAISTOS

**Fix 3 - vm_copy** (`pipeline.py`):
- BM25 retourne vm_clone au lieu de vm_copy ("copie" present dans enrichissement "clone")
- Fix: `_rule_based_detect()` intercepte "copie/transfere FILE vers/sur VM"

**Fix 4 - vm_verify** (`intent_classifier.py`, `pipeline.py`):
- IntentClassifier (Llama 1b) classe "verifie la VM" comme "info" → pipeline ignorait l'outil
- Fix: regex override `_DEMANDE_VERBS_RE` dans `classify()` force "demande" pour verbes d'action
- Fix: `_rule_based_detect()` intercepte "verifie/verif [la VM] NAME"

**Nouveaux examples EPHAISTOS** (`ephaistos.py`):
- vm_clone avec source_vm + new_vm_name
- vm_copy avec source + vm_name + dest
- vm_verify avec vm_name optionnel
- vm_clone_system avec name

**Fichiers modifies:**
- `lyra/core/pipeline.py` : `import re`, `_rule_based_detect()`, fixes `_handle_vm_clone_workflow`
- `lyra/models/intent_classifier.py` : `_DEMANDE_VERBS_RE`, exemples prompt
- `lyra/models/ephaistos.py` : 4 nouveaux exemples FEDORA

---

## [Phase 4] - 2026-01-23

### Operations Async via n8n + Fallback Subprocess

**Ajouts:**
- Module `modules/n8n.py` : Client n8n + executeur async fallback
- 3 workflows n8n crees avec noeud `code` (JS)
- Detection automatique des operations longues (vm_clone, backup_create, backup_restore)
- **Fallback subprocess** : Si n8n non disponible, execute en arriere-plan via threading
- Notification dans le terminal quand operation terminee (mode fallback)

**Workflows n8n:**
| Workflow | Webhook | Description |
|----------|---------|-------------|
| Lyra - Clone VM v2 | `/webhook/lyra-clone-vm-v2` | Clone VM via kvm-clone.sh |
| Lyra - Backup Create | `/webhook/lyra-backup-create` | Cree backup timeshift/borg |
| Lyra - Backup Restore | `/webhook/lyra-backup-restore` | Restaure backup |

**Note:** Les workflows utilisent le noeud `n8n-nodes-base.code` au lieu de `executeCommand`
(ce dernier n'etait pas reconnu par l'API).

**Fichiers modifies:**
- `main.py` : Integration n8n avec fallback subprocess
- `modules/n8n.py` : Client n8n + AsyncExecutor pour fallback
- `config.yaml` : n8n.enabled = true, webhook path mis a jour
- `prompts/system_prompt.txt` : Section operations async

**Mode fallback (subprocess):**
Quand n8n n'est pas disponible ou les webhooks ne sont pas actifs:
1. Lyra detecte l'echec du webhook
2. Lance la commande en arriere-plan via subprocess.Popen
3. Notifie dans le terminal quand c'est termine

**Configuration requise:**
```yaml
n8n:
  enabled: true
  base_url: http://localhost:5678
  api_key: <votre-cle-api>  # Optionnel
  webhooks:
    clone-vm: /webhook/lyra-clone-vm-v2
    backup-create: /webhook/lyra-backup-create
    backup-restore: /webhook/lyra-backup-restore
```

**Pour activer les webhooks n8n:**
1. Aller sur http://localhost:5678
2. Ouvrir chaque workflow Lyra
3. Cliquer sur le toggle "Active" en haut a droite
4. Les webhooks seront alors operationnels

---

## [Phase 3] - 2026-01-23

### Actions + Securite

**Ajouts:**
- Principe **Read-First** : verification automatique de l'etat VM avant toute action
- System prompt externe (`prompts/system_prompt.txt`) au lieu de hardcode
- Confirmation vocale avec mots-cles ("oui"/"non"/"oui je confirme")
- Affichage de l'etat VM dans la confirmation (status, IP)
- Description vocale naturelle des actions proposees

**Regles de securite:**
- `READ_FIRST_TOOLS` : vm_start, vm_stop, vm_destroy, vm_snapshot, vm_clone
- `READ_ONLY_TOOLS` : vm_status, backup_status, backup_list, backup_verify
- Actions dangereuses : confirmation explicite "oui je confirme" en vocal

**Fichiers modifies:**
- `main.py` : Chargement prompt externe, Read-First, descriptions vocales
- `modules/ui.py` : Confirmation vocale, affichage etat VM
- `prompts/system_prompt.txt` : Regles de securite detaillees

**Confirmation vocale:**
- Option `[v]` pour passer en mode vocal
- Mots-cles acceptes : oui, yes, ok, d'accord, confirme, vas-y
- Mots-cles annulation : non, no, annule, stop, arrete
- Actions destructives : exigent "oui je confirme"

---

## [Phase 2] - 2026-01-22

### Mode Vocal (STT/TTS)

**Ajouts:**
- Mode `--vocal` pour interaction vocale complete
- Module `modules/audio.py` : STT, TTS, AudioRecorder, VoiceInterface
- Script `run.sh` : Lancement avec configuration CUDA automatique
- Alias bash `lyra` et `lyra --vocal`
- Bip sonore avant l'ecoute
- Indicateur visuel de niveau audio en temps reel
- Detection de silence pour fin d'enregistrement automatique

**Stack vocale:**
- STT : faster-whisper (modele base, CUDA float16)
- TTS : Piper (voix fr_FR-upmc-medium)
- Audio : sounddevice avec resampling 48kHz

**Configuration (`config.yaml`):**
```yaml
audio:
  sample_rate: 48000      # Compatible PipeWire/ALSA
  silence_threshold: 0.005
  silence_duration: 1.0
stt:
  model: base
  device: cuda
  compute_type: float16
tts:
  model: fr_FR-upmc-medium
```

**Dependances ajoutees:**
- faster-whisper
- piper-tts
- sounddevice
- nvidia-cublas-cu12
- nvidia-cudnn-cu12

**Fixes techniques:**
- Resampling audio : 48kHz (PipeWire) <-> 16kHz (Whisper) <-> 22050Hz (Piper)
- `suppress_stderr()` : Masque les warnings cffi de sounddevice
- Configuration CUDA via `LD_LIBRARY_PATH` dans run.sh

**Issue connue:**
- Elgato Wave 3 non fonctionnel (necessite Wave Link sur Windows/Mac)
- Workaround : Utiliser G522 LIGHTSPEED comme micro par defaut

---

## [Phase 1] - 2024

### Wrapper Python + MCP (mode texte)

**Fonctionnalites:**
- Client Ollama avec parsing JSON des tool calls
- Client MCP pour fedora-agents
- Human-in-the-Loop : confirmation avant execution
- Interface CLI en francais
- Raccourcis clavier (Ctrl+L, double Ctrl+C)

**Outils MCP disponibles:**
- VM : vm_status, vm_start, vm_stop, vm_snapshot, vm_exec, vm_clone
- Backup : backup_status, backup_list, backup_create, backup_verify
