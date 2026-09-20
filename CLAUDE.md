# CLAUDE.md

Guide de travail pour un agent de code sur Lyra. Version condensée : l'architecture détaillée est dans `docs/`, les outils MCP dans `docs/user/MCP_TOOLS.md`.

## Ce qu'est Lyra

Assistant DevOps vocal **local par défaut** (français) : il pilote des machines virtuelles KVM, des sauvegardes et des équipements domotiques via des serveurs MCP, avec confirmation humaine avant toute action sensible. LLM via Ollama, reconnaissance vocale faster-whisper, synthèse Piper.

## Architecture V2 (RAG), mode par défaut

```
[Entrée texte ou voix] -> [IntentClassifier] -> demande | info | discussion
        demande -> [Rules] (détection règle par règle, sans LLM) -> sinon [RAG hybride] -> [TOON] -> [EPHAISTOS]
        -> [HESTIA] (exécution MCP avec confirmation) -> [LYRA] (réponse) -> [Piper TTS]
```

| Composant | Rôle | Modèle |
|---|---|---|
| IntentClassifier | classe l'intention | LYRA |
| Rules (`lyra/rules/`) | détecte les commandes courantes sans LLM | Python |
| RAG hybride (`lyra/rag/`) | retrouve les specs MCP (sémantique + BM25, 3 niveaux) | all-MiniLM-L6-v2 + ChromaDB |
| EPHAISTOS | analyse la demande et construit les arguments | `qwen2.5-coder:0.5b` |
| LYRA | dialogue et personnalité | `llama3.2:1b` |
| HESTIA (`lyra/hestia/`) | exécute les outils MCP, gère les confirmations | Python |
| Démon (`lyra/daemon/`) | pipeline résident, clients légers (texte, vocal, web) | Python |

Les modèles par défaut sont volontairement petits (environ 4 Go de VRAM au total, fonctionne aussi sur CPU avec un Ollama distant via `--ollama-host`). Les variantes 7b et 3b sont commentées dans `config.yaml.example`.

## Commandes

```bash
./run.sh                 # mode texte (RAG V2 enhanced)
./run.sh --vocal         # mode vocal STT/TTS
./run.sh -p              # mode performance : sans confirmation pour la domotique uniquement
./run.sh --legacy        # mode V1 (main.py)
make test                # tests unitaires
make smoke               # tests de fumée
make campaign            # campagnes MCP et LLM (longues, rapports générés dans tests/, non versionnés)
python3 -m pytest tests/unit/rules -q   # ce que lance la CI GitHub
```

Installation : `python3 installer/install.py` (TUI) ou `--app` (interface web locale) ; voir `installer/README.md` et `docs/user/VM_INSTALL_TESTS.md`.

## Structure

```
lyra/            paquet principal : core/ (config, constantes, validation), rules/, rag/, rag_enhanced/, hestia/, daemon/, client/, models/
modules/         STT, TTS, LLM, audio (V1 et partagé)
installer/       installeur multi-distro (Fedora, Debian, Arch) et catalogue MCP (catalog.yaml)
mcp-servers/     serveurs MCP embarqués (mermaid-mcp) ; les autres vivent dans leurs dépôts
scenes/ironman/  scène cinéma pilotée par la voix (optionnelle)
intro/           animation d'intro (Manim, chafa)
prompts/         system_prompt.txt (utilisé par main.py)
tests/           unit/, integration/, installer/, campagnes
docs/            user/ (flux de données, outils MCP, tests en VM), dev/ (architecture, RAG, INDEX_RAG.md : ordre de régénération des index, BOUCLE_AMELIORATION.md : méthode de bench itérative), archive/ (notes de phases)
```

## Sécurité : ce que le code garantit

- Confirmation obligatoire pour toute action MCP ; la liste des outils dangereux est unique : `lyra/core/constants.py` (`DANGEROUS_TOOLS`, sous-ensemble `DESTRUCTIVE_TOOLS`). Comparer toujours via `is_dangerous_tool()` (gère le préfixe serveur).
- Les outils dangereux ne sont jamais auto-confirmés, même en `-p` ou `-y`.
- Les arguments transmis aux scripts shell (noms de VM, chemins, commentaires) sont validés par liste blanche regex (`lyra/core/validation.py`).
- L'installeur copie les scripts privilégiés dans `/usr/local/lib/lyra/scripts` (root) et génère un `sudoers.d` par script (`installer/core/steps/mcps.py`).
- Sorties réseau optionnelles (Ollama distant, n8n, Notion, Discord) : désactivées sans configuration explicite.

## Workflow human-in-the-loop

Action simple : le LLM propose `{"name": "vm_start", ...}`, Lyra affiche l'action et l'état courant, attend `[O/n/d]`, exécute, puis résume. Actions multiples : liste numérotée, exécution `[T]out / [1] par 1 / [n]on`, séquentielle. Les actions longues passent en tâches asynchrones suivies par mcp-tracking.

## Conventions

- Langue : interface, voix et documentation utilisateur en français ; commits en anglais, format conventionnel (`feat:`, `fix:`, `docs:`, `chore:`).
- Aucun chemin personnel, adresse IP privée ni secret dans le dépôt : configuration par `config.yaml` / `secrets.yaml` (exemples fournis) et variables d'environnement.
- Tout bug corrigé s'accompagne d'un test de régression ; les règles de détection sont testées en table dans `tests/unit/rules/`.
- Les fichiers générés (bases ChromaDB, rapports, caches Manim) ne sont jamais versionnés (voir `.gitignore`).

## Licence

AGPL-3.0 à partir de la version 1.1.0, avec option de licence commerciale (`COMMERCIAL-LICENSE.md`) ; contributions sous `CLA.md`. La synthèse vocale utilise Piper (GPL-3.0), installé séparément par l'installeur.
