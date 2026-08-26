# CLAUDE.md

## Regles de test obligatoires

**Avant de livrer tout changement sur Lyra (UI, pipeline, modules), effectuer ces deux tests en ordre :**

1. **One-shot dry-run** — verifie que les imports et le pipeline ne plantent pas :
   ```bash
   lyra -y "liste mes VMs"
   ```
   Attendu : reponse coherente sans traceback.

2. **One-shot approche utilisateur reelle** — simule une vraie requete sans `-y` (avec confirmation) :
   ```bash
   lyra "demarre preprod-01"
   ```
   Attendu : prompt de confirmation visible, barre coloree au bon endroit, pas de corruption d'affichage.

Ne jamais livrer un changement visuel (UI) sans avoir observe le rendu dans le terminal reel.

---

## Project Overview

Lyra is a **voice-controlled DevOps assistant** providing local voice interface (French) for managing KVM virtual machines and backup systems.

## Architecture V2 (RAG) - Par defaut

```
[User Input] ──► [IntentClassifier] ──► demande/info/discussion
     │ (vocal)         │
     ▼                 ▼
[Whisper STT]    ┌─────┴─────┐
                 │           │
            [demande]   [info/discussion]
                 │           │
                 ▼           ▼
            [RAG Hybrid] ──► [LYRA]
            (Semantic+BM25)    │
                 │             ▼
                 ▼         [Reponse]
            [TOON Encode]
            (Specs compact)
                 │
                 ▼
            [EPHAISTOS]
            (Analyse specs)
                 │
                 ▼
            [HESTIA] ──► [MCP] ──► [LYRA] ──► [Piper TTS]
            (Execution)
```

### Composants V2

| Composant | Role | Modele |
|-----------|------|--------|
| **IntentClassifier** | Classification intention (demande/info/discussion) | LYRA (config: lyra.name) |
| **RAG Hybrid** | Recherche specs MCP (semantic + keyword BM25) | all-MiniLM-L6-v2 |
| **Rules** | Detection regle-par-regle (lyra/rules/detect()) avant EPHAISTOS | Python natif |
| **TOON** | Encoding compact des specs avant EPHAISTOS (~40% tokens) | Python natif |
| **EPHAISTOS** | Analyse specs, extraction arguments (si aucune regle ne matche) | config: ephaistos.name |
| **LYRA** | Dialogue, personnalite, formatage | config: lyra.name |
| **HESTIA** | Execution MCP, gestion erreurs | - |

### Modeles (config.yaml)

```yaml
models:
  ephaistos:
    name: "qwen2.5-coder:0.5b"   # Experimental 3GB - defaut actuel
    # name: "qwen2.5-coder:7b"   # Production 5GB (backup)
  lyra:
    name: "llama3.2:1b"          # Experimental 3GB - defaut actuel
    # name: "llama3.2:3b"        # Production 2.5GB (backup)
```

Note: les modeles 0.5b/1b sont les modeles experimentes actuellement. Changer dans config.yaml pour revenir aux 7b/3b.

### Pipeline reel (EnhancedPipeline wrapping Pipeline V2)

```
[User] → EnhancedPipeline (pre-processing si --rag-enhanced)
         ├─ SlangNormalizer (anglicismes → FR) [ACTIF]
         ├─ ContextInjector (historique session) [ACTIF]
         ├─ SynonymExpander [DESACTIVE - enrichissement cote indexation a la place]
         └─ Pipeline V2
              ├─ IntentClassifier
              ├─ RAG3Tier (3 collections: registry/capabilities/parameters) [ACTIF]
              │  ou V2 fallback (Semantic + BM25 + RRF) si 3-tier desactive
              ├─ rules.detect() → step 2.5: si match, skip RAG + EPHAISTOS
              ├─ EPHAISTOS → analyse specs + args (si aucune regle ne matche)
              ├─ LYRA → dialogue/confirmation
              └─ HESTIA → execution MCP
         └─ ConfidenceCascader [ACTIF]
         └─ FeedbackLoop [ACTIF]
```

### Classification des intentions

| Intent | Description | Exemple |
|--------|-------------|---------|
| **demande** | Action MCP a executer | "demarre preprod-01", "quels sont mes vm" |
| **info** | Question de connaissance | "c'est quoi vm_clone", "comment ca marche" |
| **discussion** | Conversation generale | "salut", "merci", "ok" |

---

## Architecture V1 (Legacy)

```
[User Input] ──► [Ollama/Qwen] ──► [Tool Call JSON]
     │ (vocal)                           │
     ▼                                   ▼
[Whisper STT]                   [Human-in-Loop Confirmation]
                                         │
                    ┌────────────────────┼────────────────┐
                    ▼                    ▼                ▼
              [Sync MCP]          [Async n8n]      [Fallback subprocess]
                    └────────────────────┴────────────────┘
                                         │
                                         ▼
                                [Resultat ──► LLM Resume ──► Piper TTS]
```

---

## Stack Technique

| Composant | Technologie |
|-----------|-------------|
| **LLM Backend** | Qwen 2.5 Coder 0.5b via Ollama (EPHAISTOS) -- actif |
| **LLM Frontend** | Llama 3.2 1b via Ollama (LYRA) -- actif |
| **RAG** | ChromaDB + BM25 (rank-bm25) |
| **RAG Enhanced** | SlangNormalizer [ON] + ContextInjector [ON] + FeedbackLoop [ON] + ConfidenceCascader [ON] + RAG3Tier [ON] + SynonymExpander [OFF] |
| **Rules** | lyra/rules/ : detection regle-par-regle par serveur MCP (ironman, vm, hue, denon, tv, catt, tracking) |
| **TOON** | Encodeur token-compact pour specs MCP (~40% economie) |
| **Embeddings** | all-MiniLM-L6-v2 |
| **MCP** | fedora-agents (VM/Backup), pylips-mcp (TV), hue-mcp (Lumieres), denon-mcp (Home Cinema), catt-mcp (Cast), mermaid-mcp |
| **Async** | n8n webhooks + fallback subprocess |
| **STT/TTS** | faster-whisper (CUDA) + Piper (fr_FR-upmc-medium) |

### VRAM estimee

Mode experimental (actuel) : ~4 GB total
- EPHAISTOS (Qwen 0.5B): ~0.5 GB
- LYRA (Llama 1B): ~1 GB
- Embeddings (MiniLM): ~0.5 GB
- Whisper (mode vocal): ~1.5 GB

Mode production (backup) : ~10.5 GB total
- EPHAISTOS (Qwen 7B): ~5 GB
- LYRA (Llama 3B): ~2.5 GB
- Embeddings: ~0.5 GB
- Whisper (mode vocal): ~1.5 GB

## Build Commands

```bash
./run.sh                    # Mode RAG V2 Enhanced (defaut, toujours enhanced)
./run.sh --vocal            # Mode vocal STT/TTS
./run.sh -p                 # Mode performance (domotique sans confirmation)
./run.sh --vocal -p         # Combinaison
./run.sh --legacy           # Mode V1 classique (Qwen 14B)
```

Note: `--rag-enhanced` est toujours actif en mode RAG (hardcode dans run.sh). Ce n'est pas une option separee.

## Installation (2026-08-23)

L'installeur vit dans `installer/` (les anciens scripts de
`fedora-setup/scripts/lyra-install/` sont DEPRECIES) :

```bash
./installer/install.sh            # TUI Rich (defaut)
./installer/install.sh --app      # app graphique locale (127.0.0.1:9877/ui/)
./installer/install.sh --demo     # simulation complete sans commande reelle
```

- **Core declaratif** (`installer/core/`, teste dans `tests/installer/`) :
  catalogue MCPs en YAML (`catalog.yaml` — ajouter un MCP = une entree),
  pipeline d'etapes, patch YAML in-process de config.yaml/secrets.yaml
  (secrets JAMAIS dans config.yaml), installation du demon systemd.
- **Deux frontaux** consommant le meme pipeline/events : TUI
  (`installer/tui/`, ambiance neutroncore : palette or/rose, mascottes
  ASCII de `installer/assets/mascots.json`) et app web
  (`installer/app/`, backend stdlib port 9877, frontend React pre-builde
  commite dans `app/backend/static/`, rebuild via `make installer-ui`).
- **MCPs en repos publics separes** : `marouabah/{fedora-agents,hue-mcp,
  pylips-mcp,denon-mcp,catt-mcp}`. Les dossiers `mcp-servers/{pylips,denon,
  catt}-mcp/` sont des clones (gitignores par lyra) ; idem
  `fedora-setup/scripts/agents/mcp-server` (clone de fedora-agents).
  Les serveurs acceptent `LYRA_CONFIG` (chemin explicite du config.yaml).

## Project Structure

```
lyra/
├── main.py                 # Orchestrateur V1 (legacy)
├── main_rag.py             # Orchestrateur V2 RAG (defaut)
├── config.yaml             # Configuration centralisee
├── run.sh                  # Script de lancement
├── lyra/                   # Package RAG V2
│   ├── core/
│   │   ├── config.py       # Configuration RAG
│   │   ├── pipeline.py     # Pipeline principal (~1166 lignes)
│   │   ├── retrieval.py    # Retriever hybride (Semantic + BM25 + RRF)
│   │   ├── menus.py        # Detection et affichage liste outils MCP
│   │   ├── formatters.py   # Enrichissement descriptions + formatage resultats
│   │   ├── validation.py   # Validation existence VM + contraintes
│   │   ├── types.py        # Types partages (QueryType, PipelineResult)
│   │   └── workflows/      # Workflows interactifs metier
│   │       ├── context.py      # WorkflowContext (injection deps)
│   │       ├── vm_clone.py     # Workflow clone + COW choice
│   │       ├── vm_export.py    # Workflow export custom multi-tours
│   │       ├── vm_snapshot.py  # Workflow snapshot create/list
│   │       ├── vm_start.py     # Handler confirmation demarrage
│   │       └── vm_stop.py      # Handler choix arret avant clone
│   ├── models/
│   │   ├── model_manager.py    # Orchestration LLMs
│   │   ├── ephaistos.py        # Backend Qwen 0.5b
│   │   ├── lyra_voice.py       # Frontend Llama 1b
│   │   └── intent_classifier.py # Classification intentions
│   ├── rag/
│   │   ├── semantic_retriever.py  # ChromaDB embeddings
│   │   ├── keyword_retriever.py   # BM25
│   │   ├── fusion.py              # RRF fusion
│   │   ├── indexer.py             # Indexation specs MCP
│   │   └── session_memory.py      # Contexte multi-tour
│   ├── rag_enhanced/              # Modules RAG Enhanced (toujours actifs)
│   │   ├── slang_normalizer.py    # Normalisation anglicismes (188 patterns)
│   │   ├── synonym_expander.py    # Expansion synonymes FR
│   │   ├── context_injector.py    # Injection contexte conversationnel
│   │   ├── feedback_loop.py       # Boucle feedback qualite
│   │   ├── confidence_cascader.py # Cascade de confiance multi-niveau
│   │   ├── pipeline_enhanced.py   # Pipeline Enhanced orchestrateur
│   │   └── rag_3tier.py           # RAG 3 niveaux (exact/semantic/keyword)
│   ├── rules/                     # Detection par regles (extraite de pipeline.py)
│   │   ├── base.py                # BaseRule + RuleResult
│   │   ├── vm.py                  # Regles VM (start/stop/clone/exec/verify...)
│   │   ├── backup.py              # Regles backup
│   │   ├── hue.py                 # Regles Hue (on/off/brightness/color)
│   │   ├── denon.py               # Regles Denon (volume/mute/input/power)
│   │   ├── tv.py                  # Regles TV (volume/power/youtube/ambilight)
│   │   ├── catt.py                # Regles Cast (youtube/url/stop/scan)
│   │   └── tracking.py            # Regles tracking (list/get/delete/open_ui)
│   ├── utils/
│   │   ├── toon.py                # Encodeur TOON (compact ~40%)
│   │   └── mermaid_viewer.py      # Visualisation Mermaid
│   └── hestia/
│       ├── executor.py            # Execution MCP
│       ├── background_tasks.py    # Gestionnaire taches async + persistance
│       ├── tracking_client.py     # Client HTTP tracking API (port 8765)
│       ├── metrics.py             # Metriques performance
│       └── notion_logger.py       # Logger vers Notion
├── modules/                # Modules V1 (compatibilite)
│   ├── llm.py, mcp.py, ui.py, audio.py, n8n.py
├── scripts/                # Scripts utilitaires
│   ├── async_mcp_wrapper.py   # Wrapper async: bypass JSON-RPC, poller .progress
│   ├── index_mcp_specs.py     # Indexation specs MCP dans ChromaDB
│   └── reindex_mcp_rag_optimized.py # Re-indexation optimisee
├── mcp-servers/
│   ├── pylips-mcp/         # Wrapper MCP TV Philips
│   ├── catt-mcp/           # Cast YouTube via catt
│   ├── denon-mcp/          # Controle Denon AVR via telnet
│   └── mermaid-mcp/        # Rendu diagrammes Mermaid
├── scenes/ironman/         # Scene Iron Man (Phase 6)
│   ├── orchestrator.py     # Orchestrateur principal
│   ├── run_scene.py        # Point d'entree CLI pour tests
│   ├── test_orchestrator.py
│   └── phases/
│       ├── phase0_detection.py + test_phase0.py
│       ├── phase1_blackout.py + test_phase1.py
│       ├── phase2_impact.py + test_phase2.py
│       ├── phase3_buildup.py + test_phase3.py
│       ├── phase4_transition.py + test_phase4.py
│       └── phase5_tts.py + test_phase5.py
├── data/
│   └── slang_dict.json     # 188 patterns slang (max 200)
└── prompts/                # System prompts + ironman_prompts/
```

## MCP Tools

**VM Controller**: `vm_start`, `vm_stop`, `vm_destroy`, `vm_status`, `vm_exec`, `vm_copy`, `vm_snapshot`, `vm_clone`, `vm_clone_system`, `vm_verify`

**Backup Manager**: `backup_create`, `backup_list`, `backup_restore`, `backup_verify`, `backup_clean`, `backup_status`

**TV Philips** (Phase 5): `tv.power_on/off`, `tv.volume_up/down/set`, `tv.mute`, `tv.ambilight_*`, `tv.launch_app`, `tv.youtube_video`

**Hue** (Phase 5): `hue.turn_on/off_light`, `hue.set_brightness`, `hue.set_color_rgb`, `hue.set_group_*`, `hue.activate_scene_by_name`

**Cast** (Phase 5.4): `cast_youtube`, `cast_url`, `cast_stop`, `cast_pause`, `cast_resume`, `cast_volume`, `cast_seek`, `cast_status`, `cast_scan`

**Denon** (Phase 5.5): `volume_set`, `volume_up`, `volume_down`, `mute_on`, `mute_off`, `mute_toggle`, `power_on`, `power_off`, `set_input`, `get_status`

## Securite

- **Confirmation obligatoire** pour toutes les actions MCP
- **Actions dangereuses** (jamais auto-confirmees meme en `-y`): `vm_destroy`, `vm_stop`, `vm_exec`, `vm_clone_system`, `backup_restore`, `backup_clean` (source unique: `lyra/core/constants.py DANGEROUS_TOOLS`). Sous-ensemble DESTRUCTIVE_TOOLS (prompt rouge "ACTION DESTRUCTIVE"): destroy/backup_restore/backup_clean ; les autres ont un prompt ambre "ACTION SENSIBLE". Toujours comparer via is_dangerous_tool() (gere le prefixe serveur).
- **Mode performance**: Skip confirmation pour domotique, JAMAIS pour VM/backup dangereux
- **Validation format**: `vm_name`/chemins/commentaires valides par whitelist regex avant transmission aux scripts shell (`scripts/async_mcp_wrapper.py`)

## Flux Interactif - Liste des Outils MCP

Quand l'utilisateur demande les outils disponibles, Lyra propose un menu interactif:

```
>>> donne moi la liste des mcp stp

J'ai 80 outils disponibles. Quel serveur veux-tu explorer?

  1. **CATT** (15 outils) - Cast video
  2. **DENON** (10 outils) - Home Cinema Denon AVR
  3. **FEDORA** (17 outils) - VM KVM et backups
  4. **HUE** (24 outils) - Lumieres Philips Hue
  5. **TV** (14 outils) - Controle TV Philips
  6. **TOUS** - Afficher tous les outils

>>> 3

**FEDORA** (17 outils):
  - **vm_start**: Demarre une VM KVM...
  - **vm_stop**: Arrete une VM KVM...
  ...
```

---

## Workflow Human-in-the-Loop

### Action simple
```
User: "demarre preprod-09"
    ↓
LLM genere: {"name": "vm_start", "arguments": {"vm_name": "preprod-09"}}
    ↓
Wrapper affiche: "ACTION PROPOSEE: vm_start"
                 "Etat actuel: Arrete"
                 "Executer ? [O/n/d]"
    ↓
User confirme: O
    ↓
Wrapper execute MCP → resultat
    ↓
LLM resume: "La VM preprod-09 est demarree (IP: 192.168.122.146)"
```

### Actions multiples (Todo List)
```
User: "supprime sandbox-01 et sandbox-02"
    ↓
LLM genere: {"name": "vm_destroy", "arguments": {"vm_name": "sandbox-01"}}
            {"name": "vm_destroy", "arguments": {"vm_name": "sandbox-02"}}
    ↓
Wrapper affiche: "[i] Todo list: 2 actions proposees"
                 "  [1] vm_destroy -> sandbox-01"
                 "  [2] vm_destroy -> sandbox-02"
                 "Executer ? [T]out / [1] par 1 / [n]on"
    ↓
User confirme: T (tout) ou 1 (une par une)
    ↓
Wrapper execute sequentiellement
```

## Key Constraints

- **Language**: French (UI, voice, docs)
- **Hardware**: RTX 3080 Ti (12 Go VRAM)
- **VRAM**: ~10.1 GB Qwen + ~0.5 GB Whisper
- **Offline**: 100% local

## Architecture Demon (2026-08-07)

Lyra tourne en **demon resident** (`lyra/daemon/`) + clients legers (`lyra/client/`).

- **Demon** : pipeline RAG chaud, sessions MCP ouvertes, multi-sessions
  (SessionStore + ContextVar, `Pipeline.session_scope()`), une requete active
  a la fois. Socket UNIX `~/.lyra/lyra.sock` (JSON-lines, full-duplex).
  Service systemd user `lyra-daemon` (`install/lyra-daemon.service`,
  Restart=always, PAS de NoNewPrivileges : sudo requis par virsh).
- **Protocole** : la surface UIContext (9 callables) serialisee — 7 messages
  `output`, 2 interactions `ask` (confirm/input) avec reponse `answer`.
  `RemoteUI` (lyra/daemon/remote_ui.py) est la seule piece vue par lyra/.
- **Clients** : `python -m lyra.client` route tout — one-shot et REPL via le
  demon ; `--vocal`, `--legacy`, `--debug`, `--standalone` -> main_rag
  historique. Demon mort -> relance auto (systemd puis spawn) + message
  d'accueil facon Lyra avec la raison du crash (`lyra/daemon/state.py`) +
  notification desktop. Fallback standalone si le demon refuse de demarrer.
- **Etat** : `~/.lyra/daemon_state.json` (pid, statut, heartbeat 15s).
- **Mesures** (bench `scripts/bench_daemon.py`) : one-shot pipeline complet
  17.1s -> 1.3s ; REPL pret 20s -> 0.25s ; requete chaude ~0.3-1s.
- **Pas encore via demon** : vocal (client standalone), correction "m"
  interactive, messages M1 non-verbose. Le bandeau de taches du REPL client
  lit le registre partage `~/.lyra/active_tasks.json`.
- Debug : `journalctl --user -u lyra-daemon -f` ; sante :
  `{"type":"health"}` sur le socket.

## Commandes Internes

`help`, `clear`, `clearscreen`, `quit`/`stop`, `mode`, `mode performance`, `mode default`, `/setting`

Toutes les commandes internes sont acceptees avec ou sans prefixe `/`.

## Reglages utilisateur (/setting)

Menu interactif de reglages persistants (voix TTS, vitesse de parole, mode).

- **Persistance** : `~/.lyra/settings.json`, fusionne PAR-DESSUS `config.yaml` au
  demarrage (`lyra/core/settings.py UserSettings.merged_tts`). config.yaml n'est
  jamais reecrit.
- **TUI interactif** : `lyra/core/settings_tui.py` — navigation aux fleches,
  Entree pour choisir, Echap (ou q, ou Ctrl+C) pour revenir puis fermer et
  reprendre la saisie normale. Mode cbreak + lecture os.read sur le fd
  (PAS sys.stdin.read : le buffering TextIO casserait la detection Echap
  vs sequence fleche).
- **Fallback texte** : si stdin n'est pas un TTY (pipe, tests), machine a
  etats `lyra/core/settings_menu.py SettingsMenu` geree dans la boucle REPL
  de `main_rag.py` (hors pipeline RAG — les reponses "1", "2"... ne passent
  pas par le RAG). La logique metier (persistance + hot-swap) est partagee :
  le TUI appelle `SettingsMenu.apply_*_choice()`.
- **Voix disponibles** : scan automatique de `models/*.onnx.json` — ajouter une
  voix Piper = la telecharger dans `models/` (`python -m piper.download_voices
  fr_FR-xxx --download-dir models`), elle apparait dans le menu.
- **Voix installees** : upmc (jessica/pierre), siwis, tom, mls (2 speakers),
  gilles (low). Benchmark : `scripts/bench_tts.py` (toutes < 0.6s par phrase).
- **Hot-swap** : en mode `--vocal`, `TTS.set_voice()`/`set_speed()`
  (`modules/audio.py`) rechargent la voix sans redemarrage + apercu vocal.
  En mode texte, le reglage s'applique a la prochaine session vocale.
- La scene Iron Man (`phase5_tts.py`) suit la voix choisie (fallback upmc).

## Raccourcis

| Raccourci | Action |
|-----------|--------|
| `Ctrl+L` | Efface terminal |
| `Ctrl+C` (2x <1.5s) | Quitte Lyra |
| `Ctrl+E` | Efface les taches en erreur du bandeau (clear_errors) |

## Bandeau Taches Async

Le bandeau en bas de terminal affiche les taches en cours ET les taches en erreur :

- **Taches actives** : barre de progression `[####-----] 52% Etape 2/4: ... | 7.8 Go / 14.2 Go | (63s)`
- **Taches en erreur** : restent visibles en rouge apres echec (persistent_errors)
- **Ctrl+E** : nettoie les erreurs affichees (`BackgroundTaskManager.clear_errors()`)
- Le bandeau reste actif tant que `get_displayable_tasks()` retourne des taches (actives OU en erreur)

Fichiers concernes :
- `modules/ui.py` : `_build_banner_lines(failed_tasks=...)`, `live_input()` avec `_CLEAR_ERR_SENTINEL`
- `lyra/hestia/background_tasks.py` : `persistent_errors: List[BackgroundTask]`, `get_displayable_tasks()`, `clear_errors()`
- `main_rag.py` : `completed_notifs` filtre les succes seulement (erreurs restent dans le bandeau)

---

## Phases de Developpement

- [x] **Phase 1**: Wrapper Python + MCP
- [x] **Phase 2**: Mode Vocal (STT/TTS)
- [x] **Phase 3**: Read-First + Securite
- [x] **Phase 4**: Operations async + Todo List
- [x] **Phase 5**: Controle Domotique (TV + Hue)
- [x] **Phase 6**: Scene Iron Man

---

## Phase 4 - Operations Async ✅

Operations longues executees en arriere-plan: `vm_clone` (~60s), `vm_clone_system` (~10-30min), `backup_create/restore` (~2min)

Architecture: n8n webhook → si echec → fallback subprocess avec callback.

### Configuration sudoers

Genere par l'installeur (`installer/core/steps/mcps.py`, extra `sudoers`) dans
`/etc/sudoers.d/lyra`, valide par `visudo -cf` avant activation. Les scripts de
fedora-agents sont copies en `root:root 0755` dans `/usr/local/lib/lyra/scripts`
et les regles visent UNIQUEMENT cette copie, script par script :
```bash
<user> ALL=(ALL) NOPASSWD: /usr/local/lib/lyra/scripts/agents/vm-controller/vm-start.sh
<user> ALL=(ALL) NOPASSWD: /usr/local/lib/lyra/scripts/kvm/kvm-clone.sh
...  (un par script d'entree, jamais common.sh ni les helpers _*)
<user> ALL=(ALL) NOPASSWD: /usr/bin/virsh
<user> ALL=(ALL) NOPASSWD: /usr/bin/virt-clone
<user> ALL=(ALL) NOPASSWD: /usr/bin/qemu-img
```
Interdit : glob (`*.sh`) ou chemin sous `/home` dans une regle NOPASSWD -- un
dossier inscriptible par l'utilisateur equivaut a `NOPASSWD: ALL`. Le code
applicatif (`main.py`, `modules/n8n.py`) resout les scripts via
`lyra/core/paths.py` (`LYRA_SCRIPTS_DIR` > `paths.scripts` > defaut systeme).

### Exemple workflow async
```
User: "clone preprod-09 en test-clone"
    ↓
LLM genere: {"name": "vm_clone", "arguments": {"source_vm": "preprod-09", "new_vm_name": "test-clone"}}
    ↓
Wrapper: Confirmation → Essai n8n webhook → Echec 404
    ↓
Fallback: subprocess.Popen("sudo kvm-clone.sh preprod-09 test-clone --start")
    ↓
Wrapper: "Operation lancee en arriere-plan"
    ↓
(~60s plus tard, callback)
    ↓
Terminal: "[+] [ASYNC] Operation vm_clone terminee avec succes!"
```

---

## Phase 5 - Domotique ✅

### Configuration

```yaml
tv:
  host: "192.168.1.50"       # Philips 55OLED705/12
  user: "..."
  pass: "..."                # 64 chars hex

hue:
  bridge_ip: "192.168.1.51"
  username: "<cle-api-hue>"
```

### Devices

- **TV**: Philips 55OLED705/12 @ 192.168.1.50 (JointSpace API + ADB pour YouTube)
- **Hue**: Bridge @ 192.168.1.51, 5 lumieres (group 81 = Chambre a coucher)
- **Home Assistant**: http://localhost:8123 (Docker, optionnel)

### Mode Performance

Outils domotique executes sans confirmation. Activer via `./run.sh -p` ou `mode performance`.

### YouTube via ADB

`tv.youtube_video` utilise ADB pour lancer YouTube avec compte Premium (pas de pubs). Fallback: catt.

### Cast via catt (Phase 5.4)

MCP server pour caster des videos YouTube et autres contenus vers la TV via Chromecast/DLNA.

**Prerequis**:
- `catt`: `pip install catt`
- `yt-dlp`: `pip install yt-dlp`

**Configuration** (`config.yaml`):
```yaml
catt:
  device: "55OLED705/12"  # Nom du device (voir cast_scan)
```

**Outils disponibles**:
| Outil | Description |
|-------|-------------|
| `cast_browser` | Caste la video de l'onglet actif Firefox |
| `cast_youtube` | Caste une URL YouTube sur la TV |
| `cast_url` | Caste n'importe quelle URL video/audio |
| `cast_stop` | Arrete le cast en cours |
| `cast_pause` | Met en pause |
| `cast_resume` | Reprend la lecture |
| `cast_volume` | Regle le volume (0-100) |
| `cast_seek` | Avance/recule (secondes, negatif = reculer) |
| `cast_status` | Statut du cast en cours |
| `cast_scan` | Liste les devices disponibles |

**Exemples d'utilisation**:
```
"caste la video sur la TV"           # cast_browser - onglet actif Firefox
"caste cette video: https://youtu.be/xxx"
"arrete le cast"
"mets la lecture en pause"
"avance de 30 secondes"
```

---

## Phase 5.5 - Home Cinema Denon ✅

Controle du home cinema Denon AVR-X1700H DAB via protocole telnet.

### Configuration

```yaml
denon:
  host: "192.168.1.52"       # IP du Denon AVR-X1700H DAB
  port: 23                    # Port telnet (default: 23)
  mac: "000678B4E8C8"        # MAC address (ethernet)
```

### Outils disponibles

| Outil | Description |
|-------|-------------|
| `denon.volume_set` | Regle le volume (0-98, 80 = 0dB) |
| `denon.volume_up` | Augmente le volume |
| `denon.volume_down` | Baisse le volume |
| `denon.mute_on` | Active le mute |
| `denon.mute_off` | Desactive le mute |
| `denon.mute_toggle` | Toggle le mute |
| `denon.power_on` | Allume le Denon |
| `denon.power_off` | Eteint le Denon (standby) |
| `denon.set_input` | Change la source (BD, TV, GAME, SAT/CBL, DVD, MPLAY) |
| `denon.get_status` | Statut du Denon (volume, power) |

### Redirection automatique HDMI ARC

**IMPORTANT:** Quand un home cinema est connecte en **HDMI ARC/eARC** a la TV :
- Le volume de la TV est desactive (sortie audio via HDMI)
- Les commandes `tv.volume_*` et `tv.mute` sont **automatiquement redirigees** vers `denon.*`
- Vous pouvez utiliser indifferemment `tv.volume_set 44` ou `denon.volume_set 44`

Le serveur `pylips-mcp` detecte automatiquement si un Denon est configure et redirige les commandes volume/mute vers le Denon.

### Echelle de volume

- **0-98** : Echelle Denon (0 = -80 dB, 80 = 0 dB reference, 98 = +18 dB)
- Pour une ecoute normale : **30-50**
- Pour un home cinema : **50-70**
- Maximum recommande : **80** (0 dB)

### Sources d'entree

- `BD` : Blu-ray / Lecteur BD
- `TV` : Entree TV
- `GAME` : Console de jeu
- `SAT/CBL` : Satellite / Cable
- `DVD` : Lecteur DVD
- `MPLAY` : Media Player

Aliases supportes : `bluray`, `blu-ray`, `cable`, `sat`, `media`, `mediaplayer`

### Exemples d'utilisation

```
"passe le volume a 44"              # denon.volume_set 44 (via tv.volume_set redirige)
"monte le volume"                    # denon.volume_up (via tv.volume_up redirige)
"mets le son en mute"               # denon.mute_on
"change la source en bluray"        # denon.set_input BD
"allume le denon"                   # denon.power_on
```

---

## Phase 6 - Scene Iron Man

Experience immersive ~33s synchronisant TV + Hue sur trigger vocal "je suis iron man".

### Timeline

| Phase | Duree | Description |
|-------|-------|-------------|
| 0-Detection | 2s | Validation devices + sauvegarde rollback |
| 1-Blackout | 3s | Noir total |
| 2-Impact | 3.5s | Flash blanc + bleu + YouTube AC/DC + Ambilight |
| 3-Buildup | 12s | Pulsations rouge/bleu 120 BPM, brightness 0→254 |
| 4-Transition | 7s | Ralentissement + stabilisation bleu @150 |
| 5-TTS | 5.5s | Voix J.A.R.V.I.S. + pulse confirmation |

### Workflow Claude Code

Quand l'utilisateur dit "phase suivante" ou "continue phase 6":
1. Trouver la premiere sous-phase `[ ]` non cochee ci-dessous
2. Lire `prompts/ironman_prompts/XX_phaseY/PROMPT.md`
3. Implementer dans `scenes/ironman/`
4. Cocher `[x]` dans ce fichier

### Sous-phases

- [x] **6.0**: Detection & Validation
- [x] **6.1**: Blackout Dramatique
- [x] **6.2**: Premier Impact
- [x] **6.3**: Pulsations Synchronisees
- [x] **6.4**: Transition & Stabilisation
- [x] **6.5**: TTS J.A.R.V.I.S.
- [x] **6.6**: Orchestrateur
- [x] **6.7**: Integration Lyra (rules/ironman.py, executor interception, ChromaDB indexation)
- [x] **6.8**: Suite de Tests

### Triggers Vocaux

"je suis iron man", "je suis tony stark", "je suis tony", "mode iron man", "scene iron man"

### Configuration

```yaml
scenes:
  ironman:
    enabled: true
    triggers: ["je suis iron man", "je suis tony stark", "mode iron man"]
    youtube_video_id: "pAgnJDJN4VA"
    tts_phrase: "random"
```

### State Machine

```
IDLE → VALIDATING → BLACKOUT → IMPACT → BUILDUP → TRANSITION → TTS → STABLE
  ↑                                                                     │
  └──────────────────────── ROLLBACK ◄──────────────────────────────────┘
```

### Gestion Erreurs

- Phase 0 echoue → annuler, rester IDLE
- Phase 1-5 echoue → rollback auto
- TV/Hue offline → annuler scene
- YouTube echoue → continuer lights-only

### Structure Fichiers

```
scenes/ironman/
├── orchestrator.py
├── run_scene.py        # Point d'entree CLI pour tests manuels
├── test_orchestrator.py
└── phases/
    ├── phase0_detection.py  + test_phase0.py
    ├── phase1_blackout.py   + test_phase1.py
    ├── phase2_impact.py     + test_phase2.py
    ├── phase3_buildup.py    + test_phase3.py
    ├── phase4_transition.py + test_phase4.py
    └── phase5_tts.py        + test_phase5.py
```

---

## MCP Tracking

Lyra integre le MCP tracking pour suivre toutes ses operations longues (VM, backup, clone, export...).

### Architecture

- **Serveur tracking** : `/home/amineutron/dev/MCP/tracking/server.py` (stdio MCP + API HTTP)
- **API HTTP** : `127.0.0.1:8765` (via `api.py`) — interface utilisee par Lyra
- **Template** : `lyra_task` (champs extra : `operation`, `target`, `phase`, `eta`)
- **Dashboard** : `server.py --ui [--filter lyra_task]` — ouvert dans Kitty

### Fichiers cles

| Fichier | Role |
|---------|------|
| `lyra/hestia/tracking_client.py` | Client HTTP vers api.py (create/update/complete/error/list/get/delete/open_ui) |
| `lyra/hestia/background_tasks.py` | Auto-feed : create au lancement, complete/error a la fin |
| `scripts/async_mcp_wrapper.py` | Poller progression .progress -> PUT /sessions/{id} en temps reel |
| `lyra/hestia/executor.py` | Routage tracking.* vers TrackingClient |
| `lyra/core/pipeline.py` | Regles _rule_based_detect pour tracking.list/get/delete/open_ui |

### Commandes vocales

| Phrase | Action |
|--------|--------|
| "affiche le tracking" | open_tracking_ui() — Kitty |
| "affiche les erreurs" | open_tracking_ui(filter_template="errors") |
| "taches en cours" | tracking.list(template=lyra_task, status=running) |
| "statut de la tache abc123" | tracking.get(session_id=abc123) |
| "supprime la tache abc123" | tracking.delete(session_id=abc123) |

### Coexistence active_tasks.json / tracking_state.json

- `~/.lyra/active_tasks.json` : source de verite Lyra (PID, subprocess, redemarrage) — inchange
- `/home/amineutron/dev/MCP/tracking/tracking_state.json` : source de verite dashboard
- `tracking_id` dans active_tasks.json = lien entre les deux

---

## Bugs Connus et Fixes

| Bug | Fichier | Solution |
|-----|---------|----------|
| backup_status erreur arithmetique | backup-status.sh | Nettoyer variable count |
| LLM ne genere pas JSON | system_prompt.txt | Instructions explicites |
| vm_status 1 seule VM | common.sh | `ssh -n` |
| beep_short callback error | ui.py | `sd.OutputStream.write()` |
| JSON dans markdown | llm.py | Strip ```json blocks |
| Hue group 0 inexistant | mcp.py | Utiliser group 81 |
| Scenes Hue par ID | hue_server.py | `activate_scene_by_name` |
| Volume TV +1 au lieu de +5 | server.py | Lire/modifier volume actuel |
| Ambilight reste blanc | server.py | Ajouter `menuSetting` |
| YouTube deep linking | server.py | ADB au lieu de JointSpace |
| hue-mcp pollue stdout | hue_server.py | `print(..., file=sys.stderr)` |
| Elgato Wave 3 capture nulle | - | Workaround: G522 par defaut |
| vm_clone_system capture par vm_clone | pipeline.py | Exact match: `tool in ("vm_clone", "fedora.vm_clone")` |
| vm_clone NullPointerError source_vm=None | pipeline.py | Null-check + regex fallback dans `_handle_vm_clone_workflow` |
| vm_clone EPHAISTOS 0.5b args non extraits | pipeline.py | `_rule_based_detect()`: regex "clone X en Y" |
| vm_copy RAG retourne vm_clone ("copie" dans enrichissement "clone") | pipeline.py | `_rule_based_detect()`: regex "copie FILE vers VM" |
| vm_verify IntentClassifier dit "info" | intent_classifier.py | Regex override: verbes d'action toujours "demande" |
| "c'est quoi vm_clone" classe "demande" -> fallback "je n'ai pas compris" | intent_classifier.py | Regex override _KNOWLEDGE_RE (EXPLICIT_KNOWLEDGE_PATTERNS) teste AVANT les verbes d'action |
| vm_verify RAG retourne vm_clone | pipeline.py | `_rule_based_detect()`: regex "verifie VM" |
| backup_status watch=True → MCP boucle infinie (timeout 124) | pipeline.py | `_rule_based_detect()`: status+backup → backup_status({}) sans watch |
| vm_status listing global: vm_name='' → EXEC_ERROR | pipeline.py | `_rule_based_detect()`: "mes VMs/toutes" sans vm_name → vm_status({}) |
| vm_exec: ls() retourne au lieu de vm_exec | pipeline.py | `_rule_based_detect()`: "execute CMD sur VM" → vm_exec(vm_name, cmd) |
| backup_verify: argument type= au lieu de vm_name | ephaistos.py | Nouvel exemple FEDORA avec vm_name correct |
| backup_create: vm_name absent des arguments | ephaistos.py | Nouvel exemple FEDORA avec vm_name |
| HUE turn_on_group: ChromaDB embedding confus, retourne allume() | pipeline.py | `_rule_based_detect()`: "allume les lumieres" → turn_on_group(group_id=81) |
| HUE turn_off_light: BM25 double-scoring turn_off_group toujours gagne | pipeline.py | FRENCH_ENRICHMENTS: retire verbes de turn_on/off_group; rule pour turn_off_light |
| TV volume_up/down/mute: EPHAISTOS 0.5b retourne power_on/off | pipeline.py | `_rule_based_detect()`: "volume/son + tv/tele" → tv.volume_up/down/mute |
| TV vm_start collision: "lance Netflix sur la TV" → vm_start | pipeline.py | vm_start rule: exclusion contexte TV via regex |
| DENON power_off: eteins() mauvais outil | pipeline.py | `_rule_based_detect()`: "eteins + denon" → denon.power_off |
| DENON volume_set: BM25 retourne hue.set_brightness | pipeline.py | `_rule_based_detect()`: "volume + chiffre + denon" → denon.volume_set(level) |
| DENON mute_off: denon(status='off') mauvais format | pipeline.py | `_rule_based_detect()`: "demute/unmute + denon" → denon.mute_off |
| CATT cast_scan: SlangNorm "cast"→"diffuse" casse la detection | pipeline.py | `_rule_based_detect()`: "scan + cast/diffuse/appareils" → cast_scan |
| CATT cast_volume: SlangNorm + intent=knowledge | pipeline.py | `_rule_based_detect()`: "volume + cast/diffuse/chromecast" → cast_volume |
| HUE turn_off_group manquant: "eteins les lumieres" → aucune action | pipeline.py | `_rule_based_detect()`: "eteins + les lumieres" → hue.turn_off_group(81) |
| DENON mute_toggle manquant: "bascule le mute" → mute_on | pipeline.py | `_rule_based_detect()`: "toggle/bascule/inverse" AVANT mute_on → denon.mute_toggle |
| DENON set_input manquant: RULE_MISS total | pipeline.py | `_rule_based_detect()`: "source + alias" → denon.set_input(input) |
| DENON get_status manquant: RULE_MISS total | pipeline.py | `_rule_based_detect()`: "status/etat + denon" sans chiffre → denon.get_status |
| HUE set_brightness partiel: "lumieres a 50%", "luminosite a 30" RULE_MISS | pipeline.py | `_rule_based_detect()`: patterns supplementaires + "monte/baisse la luminosite" |
| TV screen_off inoperant: JointSpace node 2130968759 retourne 200 mais aucun effet en mode Android | server.py | Limitation firmware Philips: MUTE_SCREEN ne fonctionne qu'en source HDMI/TV (pas launcher Android). VIDMGR_PROPERTY_SCREEN_OFF require root. Fallback: screensaver DreamerService via ADB. |
| tv.power_on timeout 10s quand TV completement eteinte | server.py | Fix: connect_timeout=1.5 pour detection rapide + WoL (wakeonlan lib, MAC AA:BB:CC:DD:EE:FF). Sequence: check powerstate -> Standby key -> POST powerstate On -> WoL si injoignable. |
| vm-import.sh df retourne 0 si POOL_DIR inexistant | vm-import.sh | Fix: traverser vers le premier parent existant avant df -BG. |
| vm-import.sh tar tzf bloque sur archive 14GB (etape 1 a 10% pendant 3+ min) | vm-import.sh | Fix: remplacer tar tzf (lecture complete) par tar tzf \| head -20 (lecture partielle). |
| power_on depuis veille profonde : WoL envoye puis abandon ("attends 15-20s") ; depuis demi-veille : re-WoL au lieu de l'API | mcp-servers/pylips-mcp/server.py | Sequence auto-suffisante : WoL -> poll joignabilite (25s) -> touche Standby -> POST powerstate On (idempotent) -> VERIFICATION etat reel avant de repondre. Timeout MCP tv 10s -> 60s. 11 tests unitaires (API simulee, 3 chemins). Note: la TV met >20s a quitter l'etat "On" apres une mise en veille (transition firmware). |
| Ambilight "en blanc/violet" -> ambilight_on generique au lieu de la couleur | lyra/rules/tv.py | Meme regex fautif que hue (blanche?/violette?). Fix identique + tests paradigmatiques : CHAQUE cle des dicts couleurs est testee (26 formes). |
| Index RAG : 5 outils mermaid.* fantomes dans les 4 collections | .chromadb | Serveur mermaid absent de config.yaml -> selection possible mais execution impossible. Purge (16 entrees). Pour reactiver : ajouter le serveur dans config.yaml puis reindexer. |
| "met les lumieres en blanc" -> screen-manager.open_url(url=hue.turn_on_group) | lyra/rules/hue.py + .chromadb | Double cause: regex couleur "blanche?" ratait "blanc" (idem "violet") -> fallback RAG ; et 6 outils fantomes screen-manager.* dans lyra_mcp_specs_v2 (serveur supprime). Fix: regex blanc(?:he)?/violet(?:te)? + purge des fantomes de l'index. |
| tv.power_on "wakeonlan non installe" via demon | install/lyra-daemon.service | Les MCP sont spawnes avec "command: python" ; sous systemd le PATH resolvait le python pyenv (sans wakeonlan) au lieu du venv. Fix: Environment=PATH avec .venv/bin en tete + platform-tools (adb). |
| REPL demon : requetes silencieuses apres annulation (Ctrl+C pendant confirmation) | lyra/client/repl.py | Le cancel laissait le result tardif du demon dans le tampon -> toutes les requetes suivantes decalees d'un cran. Fix: toute annulation ferme et rouvre la connexion (flux propre garanti). Double Ctrl+C (<1.5s) quitte le REPL. |
| tv.launch_app inoperant: JointSpace activities/launch retourne 200 mais n'ouvre pas les apps Android TV | pylips/tv_server.py | Fix: ADB `am start -n pkg/class` si class_name fourni, sinon `monkey -p pkg -c LEANBACK_LAUNCHER 1`. Note: dumpsys activity top montre toujours org.droidtv.playtv en fond — verifier le vrai focus via `dumpsys window \| grep mCurrentFocus`. |
| vm_destroy "Echec de la suppression" via daemon : double cause | fedora-setup vm-destroy.sh | 1) confirmation interactive interne impossible en non-TTY -> garde [[ ! -t 0 ]] (la confirmation humaine a deja eu lieu cote Lyra) ; 2) virsh refuse un domaine avec snapshots -> --snapshots-metadata + stderr virsh remonte au lieu de &>/dev/null. |
| Confirmation destructive illisible ("Je vais executer X. Tu confirmes?") | lyra/daemon/remote_ui.py | build_confirm_prompt() a 2 niveaux : "!! ACTION DESTRUCTIVE !!" (rouge) pour DESTRUCTIVE_TOOLS (destroy/backup_restore/backup_clean), "! ACTION SENSIBLE !" (ambre) pour le reste de DANGEROUS_TOOLS (vm_stop/vm_exec/vm_clone_system — rien n'est detruit). Le chat neutroncore rend rouge ou ambre selon le texte. Tests: tests/unit/test_confirm_prompt.py |
| actions.py : "fedora.vm_clone_system" not in DANGEROUS_TOOLS (noms courts) -> is_dangerous=False -> reponse VIDE confirmait un outil dangereux | lyra/daemon/actions.py + core/constants.py | Helper is_dangerous_tool()/is_destructive_tool() normalisant le prefixe serveur (split(".")[-1]), utilise partout. Regression: test_prefixe_serveur_reconnu_dangereux |
| Multi-tour clone systeme : "Test-vm" ou "le nom est X" jamais capte (EPHAISTOS 0.5b hallucine "snapshots preprod-12") + recap "VM source : None" | core/pipeline.py + rules/vm.py | Extraction DETERMINISTE extract_clone_system_name() dans _process_pending_action (nom brut, "le nom est X", "nomme-la X", "c'est X") — le LLM n'est plus consulte pour cet arg unique. Recap dedie clone_system ("ton PC -> nouvelle VM X"). Tests: tests/unit/test_clone_system_pending.py |
| Clone systeme lance via chat : echec immediat silencieux + session tracking zombie "running 0%" | scripts/async_mcp_wrapper.py + daemon/server.py + kvm-clone-system.sh | Triple cause : 1) wrapper sans sudo -> check_root echoue (fix: finalize_cmd() prefixe sudo -n pour vm_clone_system/backup_*) ; 2) /tmp/kvm-clone-system-debug.log residu root + set -e -> mort ligne 43 (fix: fallback mktemp) ; 3) fin de tache detectee UNIQUEMENT si un REPL poll tasks_snapshot (fix: thread _watch_tasks 5s dans le daemon -> tracking complete/error garanti). Progression live: flag --tracking-id passe au script (sudo env_reset tue les variables). Tests: test_async_wrapper_cmd.py |
| Clone systeme : 2 echecs "grub2-install keylayouts.mod ENOSPC" a 91% | kvm-clone-system.sh | Triple decouverte : 1) /home est un BIND MOUNT du NVMe -> --one-file-system ne copiait AUCUN home (passe rsync dediee ajoutee, patterns re-ancres /home/* -> /*) ; 2) exclusions light elargies (Steam 342G, vms, containerd, /usr/share/ollama, profils Chrome = cookies exploitables) + disque 80G defaut ; 3) VRAIE cause ENOSPC : partition /boot du clone 1G alors que l'hote a 884M dans /boot -> 2G. 3e run OK : 46G reels, VM bootee. |
| Clone systeme 4e run : boote mais emergency mode "/dev/fedora_neutron00/root does not exist" | kvm-clone-system.sh + kvm-fix-boot.sh | rd.lvm.lv= est le PREMIER param de GRUB_CMDLINE_LINUX (pas d'espace devant) -> les sed " rd.lvm.lv" le rataient et grub2-mkconfig le reinjectait dans les BLS. Fix: patterns sans espace de tete + squeeze. Nouveau kvm-fix-boot.sh (nbd + mount p2 + purge BLS/grubenv via grub2-editenv, JAMAIS sed sur grubenv taille fixe) repare un clone existant sans re-cloner. Valide: VM boote, IP 192.168.122.x, login tty1 (l'hote n'a pas de DM — Hyprland au login). |
| VM clonee VOLE l'identite tailscale de l'hote au boot (tailnet montre "electron-01" sur l'IP 100.x du PC, telephone coupe de neutroncore) | kvm-clone-system.sh + kvm-sanitize-vm.sh | /var/lib/tailscale (cle de noeud), cles hote SSH, machine-id et PSK WiFi NetworkManager partaient dans le clone. Fix: exclusions de BASE (pas seulement light) + machine-id blanchi dans l'adaptation. kvm-sanitize-vm.sh desinfecte un clone existant (nbd + mount p3). L'hote reprend son identite des que la VM s'arrete. |
| Audit tests 2026-08-15 : 42 erreurs fixtures (pipeline._session/_ctx devenus des properties au refactor demon — integration+e2e casses depuis une semaine, invisibles car seul tests/unit/ tournait) | tests/integration + tests/e2e | Fixtures reecrites : _sessions["default"]=SessionMemory(...) + suppression des assignations _ctx (la property le reconstruit). 1021 tests verts. |
| Outillage tests 2026-08-15 (2e passe) : Makefile (make test/smoke/campaign), scripts/smoke_mcps.py (spawn+initialize+tools/list par serveur MCP, latences, report tracking ; AJUSTABLE : ne teste que les serveurs de config.yaml, 0 serveur = exit 0, --only tv,hue pour un sous-ensemble, seuils via LYRA_SMOKE_TIMEOUT/LYRA_SMOKE_SLOW), timer lyra-mcp-smoke 08:45 quotidien | Makefile + scripts/smoke_mcps.py + install/lyra-mcp-smoke.* | 5/5 serveurs < 0.5s init. Cache embeddings module (_EMBEDDING_MODEL_CACHE) : suite 132s -> 112s. Tests preprod-09 reactives avec fedora-base. MCP fedora-agents : 9 tests zod (npm test), defaut disk 80G aligne. Flag start preserve dans le flux COW de vm_clone. Proxy tracking timeout 3->6s (502 sous IO). |
| Campagne flaky : "etat des sauvegardes" puis "volume denon a 44" -> IntentClassifier KNOWLEDGE un run sur deux (ordres SANS VERBE -> Llama 1b aleatoire) | intent_classifier.py | _DEMANDE_VERBS_RE etendu : "etats? de/des/du + vm/machine/backup/sauvegarde" + noms de commande domotique (volume, luminosite, ambilight, sourdine — sans danger, _KNOWLEDGE_RE teste AVANT). Exit code campagne : PARTIAL tolere (outil correct, workflow interactif) — seuls FAIL et RULE_MISS font echouer le run. |
| Campagne flaky (cause racine) : 12 requetes de la campagne n'etaient couvertes par AUCUN regex deterministe -> classification confiee au Llama 1b -> 1 echec ALEATOIRE par run, jamais la meme requete (etat des sauvegardes, volume denon a 44, purge les sauvegardes...) | intent_classifier.py + core/types.py | Audit exhaustif : script croisant TESTS de la campagne avec les 4 regex (smalltalk/knowledge/vm_question/demande) -> 12 trous identifies d'un coup. Verbes ajoutes (start/stop/efface/envoie/dashboard/restore/controle/purge/ouvre/joue) + "comment ca marche" ajoute aux EXPLICIT_KNOWLEDGE_PATTERNS (les questions restent des questions). Couverture: 0 requete livree au LLM. Preuve: 3 campagnes consecutives identiques (151/152, 0 FAIL). Tests: test_normalized_forms.py (25 formes + 6 questions temoin). |
| Campagne one-shot 144->151/152 : "system-clone-final" declenchait vm_clone_system (gate mot isole + verbe clone requis) ; SlangNormalizer produit "statut"/"active le son"/"desactive le coupe le son" que backup/denon ne comprenaient pas ; IntentClassifier 1b flaky sur booter/coupe/monte/baisse (ajoutes au regex demande, deterministes) ; "clone X en Y et demarre" -> start:True | rules/vm.py, backup.py, denon.py, intent_classifier.py | Regressions: tests/unit/test_normalized_forms.py (15 tests). Le 1 PARTIAL restant est environnemental (la campagne clone preprod-01, VM fictive — le workflow valide l'existence reelle, comportement correct). |
| "comment vas tu ?" -> demande -> fallback "je n'ai pas compris" | intent_classifier.py | _SMALLTALK_RE (salutations/politesse) teste en premier -> discussion. Tests: tests/unit/test_intent_overrides.py |
| "c'est quoi arch-base" -> info -> hallucination LYRA (invente une description) | intent_classifier.py + rules/vm.py | _VM_QUESTION_RE (nom avec tirets, sans underscore) -> demande, teste AVANT knowledge ; regle "c'est quoi VMNAME" -> vm_status(detailed). Les noms d'outils (vm_clone) restent info. |
| vm_start echoue "code 1" sans explication quand le disque externe est debranche | fedora-setup vm-start.sh | Pre-check du disque (virsh domblklist) : message explicite "disque externe non monte (/mnt/ext-backup)" + stderr virsh remonte. |
| "met les lumieres en blanc" -> set_color_rgb({r,g,b}) : 4 erreurs Pydantic (light_id/red/green/blue requis) | lyra/rules/hue.py | La regle couleur envoyait des args {r,g,b} au mauvais outil (unitaire au lieu du groupe). Fix: hue.set_group_color_rgb avec {red,green,blue}. Regression: tests/unit/test_rules_hue_couleur.py. |

---

## Development Notes

- MCP server: `/home/amineutron/dev/fedora-setup/scripts/agents/mcp-server/`
- MCP timeout: 120s
- Wrapper parse JSON du content (pas tool_calls natif)
- Double Ctrl+C (< 1.5s) pour quitter
