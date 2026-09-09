# Flux de données de Lyra : ce qui est capté, ce qui est gardé, ce qui sort

Lyra est **locale par défaut** : le traitement de la voix, le LLM, la recherche et l'exécution des outils tournent sur votre machine. Ce document répond aux questions qu'un responsable informatique pose avant d'installer un assistant qui écoute et agit.

## Ce que Lyra capte et où ça va

| Donnée | Capté par | Stocké où | Combien de temps | Purger |
|---|---|---|---|---|
| Voix (micro) | `sounddevice`, en mode vocal seulement | jamais écrite sur disque : transcrite en mémoire par faster-whisper puis jetée | 0 | rien à faire |
| Texte des requêtes et réponses | le démon | `data/session_history.db` (SQLite, en clair) | fenêtre glissante des 15 derniers échanges | `rm data/session_history.db` |
| Retours utilisateur (« c'était bien / pas bien ») | RAG enhanced | `data/feedback.json` | jusqu'à suppression | `rm data/feedback.json` |
| Index des spécifications d'outils | indexeur RAG | `.chromadb/` (embeddings locaux) | jusqu'à réindexation | `rm -rf .chromadb && make index` |
| Réglages (voix, modèles) | menu `/setting` | `~/.lyra/settings.json` | jusqu'à modification | supprimer le fichier |
| Erreurs | journal d'erreurs | `~/.lyra/logs/errors/` | rotation par le démon | supprimer le dossier |
| Socket du démon | démon | `~/.lyra/lyra.sock` (UNIX, droits 0600) | durée d'exécution | automatique |
| Journal des actions MCP | mcp-tracking | `~/.local/state/tracking/` (via l'API locale 127.0.0.1:8765) | purge automatique (7 jours après la fin) | API tracking |

Aucun de ces fichiers n'est envoyé ailleurs. Les secrets (jetons, mots de passe d'équipements) sont dans `secrets.yaml`, jamais dans les journaux.

## Les sorties réseau, toutes optionnelles

| Sortie | Vers | Activée par | Ce qui part |
|---|---|---|---|
| Ollama distant | la machine indiquée par `--ollama-host` ou `llm.base_url` | vous, à l'installation | le texte des requêtes, en HTTP sur votre réseau ; par défaut `localhost:11434` |
| mcp-tracking | `127.0.0.1:8765` (local) | `tracking.enabled` | nom et progression des actions longues |
| n8n | `n8n.base_url` (par défaut `localhost:5678`) | `n8n.enabled` | déclenchement des tâches asynchrones (clone de VM, sauvegarde) |
| Discord | `discord.webhook_url` | `discord.enabled` **et** un webhook renseigné dans `secrets.yaml` | notifications de fin de tâche et d'erreur (titre, état) |
| Home Assistant | `homeassistant.url` | `homeassistant.enabled` **et** un jeton | commandes domotiques |
| Notion | API Notion | `notion.enabled` (désactivé par défaut) **et** un jeton | journal des workflows |
| Installeur | `ollama.com`, `huggingface.co`, `pypi.org` | à l'installation seulement | téléchargement des modèles, de Piper et des dépendances |

Sans configuration explicite (jeton, URL), chacune de ces sorties est inactive : `enabled: true` seul ne suffit pas. Pour un usage strictement hors ligne, mettre `enabled: false` sur n8n, Discord, Home Assistant et Notion, et pointer Ollama sur la machine locale.

## Ce que Lyra ne fait jamais

- Aucun appel à un fournisseur de LLM en ligne (OpenAI, Google, Anthropic…) : il n'y a pas de client pour cela dans le code.
- Aucune télémétrie, aucun compteur d'usage envoyé à l'auteur.
- Aucune exécution d'action sensible sans confirmation humaine : voir la section Sécurité du README.

## Vérifier par vous-même

```bash
grep -rn "https\?://" lyra modules | grep -v "127.0.0.1\|localhost"   # les seules URL externes sont celles ci-dessus
ss -tnp | grep python                                                   # connexions ouvertes par le démon
```
