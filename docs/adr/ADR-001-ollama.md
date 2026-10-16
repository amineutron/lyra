# ADR-001 — Ollama comme moteur des modèles

## Contexte

Lyra doit tourner sur la machine de l'utilisateur, sans compte ni facture, avec deux modèles
chargés en permanence (analyse des commandes et dialogue). Il faut aussi pouvoir déporter
l'inférence sur une autre machine : poste sans carte graphique, Codespace, conteneur.

## Décision

Les modèles sont servis par [Ollama](https://ollama.com), appelé en HTTP (`/api/chat`,
`/api/tags`) par [`lyra/models/model_manager.py`](../../lyra/models/model_manager.py).

- Adresse : `OLLAMA_HOST` prime sur `llm.base_url` de `config.yaml`, puis `http://localhost:11434`
  (`RAGConfig.get_ollama_base_url`, [`lyra/core/config.py`](../../lyra/core/config.py)). Un hôte
  seul devient `http://hôte:11434` ; une URL complète est gardée telle quelle.
- Les modèles restent en mémoire (`keep_alive: -1`) et le contexte est fixé à 8192 jetons : le
  défaut d'Ollama (4096) tronquait le prompt d'EPHAISTOS, d'environ 6100 jetons (mesure du
  2026-09-17).
- Installation locale par le script officiel, ou Ollama distant avec `--ollama-host` : l'installeur
  écrit alors `llm.base_url` et `OLLAMA_HOST`, et n'installe que le client
  ([`installer/core/steps/ollama.py`](../../installer/core/steps/ollama.py)).
- Conteneurs : `docker-compose.sovereign.yml` fige une image Ollama, profils `cpu` et `gpu`.

## Alternatives

- **Fournisseur de modèles en ligne** : écarté par principe (local par défaut). Lyra n'a pas de
  client pour un tel service ([Flux de données](../user/DATA_FLOWS.md)).
- **llama.cpp, vLLM, LM Studio** : aucun essai documenté. Ollama est là depuis la phase 1 (2024)
  ; la feuille de route prévoit un moteur compatible OpenAI pour d'autres serveurs locaux.

## Conséquences

- Un seul binaire à installer, des modèles nommés (`llama3.2:1b`), un serveur partageable sur le
  réseau.
- Un Ollama distant est joint **en HTTP clair, sans authentification** : le texte des requêtes
  traverse le réseau, et ce serveur choisit l'outil et ses arguments. Voir le
  [modèle de menaces](../THREAT_MODEL.md).
- Derrière un proxy, seule la boucle locale est ajoutée à `NO_PROXY`
  ([`lyra/utils/netenv.py`](../../lyra/utils/netenv.py)) : un Ollama distant du réseau interne
  passe par le proxy si `HTTP_PROXY` est défini, sauf à l'ajouter soi-même à `NO_PROXY`.
