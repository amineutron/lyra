# Ajouter un serveur MCP

Lyra ne connaît pas votre infrastructure : elle la pilote au travers de serveurs
[MCP](https://modelcontextprotocol.io/). Les serveurs fournis (machines virtuelles, sauvegardes,
domotique) ne sont que des exemples ; n'importe quel serveur MCP qui parle sur l'entrée et la
sortie standard peut s'ajouter, sans toucher au code de Lyra.

## 1. Déclarer le serveur

Dans `config.yaml`, une entrée sous `mcp.servers`. La clé (`stock` ci-dessous) devient le
préfixe de ses outils : `stock.liste_articles`, `stock.reserver`…

```yaml
mcp:
  servers:
    stock:
      enabled: true
      command: /opt/mcp-stock/.venv/bin/mcp-stock   # chemin absolu : session persistante
      args: ["--lecture-seule"]
      env:
        STOCK_API_URL: "https://stock.interne"
      timeout: 30          # secondes par appel (60 par défaut)
```

| Clé | Rôle |
|---|---|
| `enabled` | `false` pour le garder sans le lancer |
| `command` | ce qui démarre le serveur (voir ci-dessous) |
| `args` | arguments de la commande |
| `env` | variables d'environnement passées au serveur |
| `timeout` | délai maximal d'un appel, en secondes |

La forme de `command` décide de la façon dont Lyra lance le serveur :

| `command` | Lancement |
|---|---|
| chemin absolu (`/…` ou `~/…`) | **session persistante** : un processus gardé ouvert, `args` et `env` transmis. La forme à préférer. |
| `python` ou `python3` avec `args: ["-m", "module"]` | `python3 -m module` à chaque appel |
| `python` ou `python3` avec un script | `python3 <script>` à chaque appel (seul le premier argument est repris) |
| `node` | `node <args[0]>` à chaque appel (`env` n'est pas transmis) |

Toute autre commande (`npx`, `uv`, `docker`…) est refusée au démarrage avec le message
« Type de serveur non supporte ». Pour un serveur qui se lance ainsi, écrire un petit script
exécutable et donner son chemin absolu.

Ne pas utiliser `tracking`, `ironman`, `vm` ni `backup` comme clé : ces préfixes sont déjà
interceptés par Lyra.

## 2. Indexer ses outils

Lyra retrouve l'outil à appeler par recherche sémantique dans un index de leurs descriptions.
Cet index n'est **pas** reconstruit au démarrage : après l'ajout d'un serveur (ou d'un outil),
on le refait, serveur démarré et joignable, depuis la racine du dépôt :

```bash
.venv/bin/python scripts/reindex_mcp_rag_optimized.py   # lit les outils de chaque serveur (tools/list)
.venv/bin/python scripts/index_rag_3tier.py --clear     # reconstruit l'index utilisé par le démon
systemctl --user restart lyra-daemon.service            # le démon garde l'index en mémoire
```

Un serveur injoignable au moment de l'indexation disparaît de l'index : ses outils ne seront plus
trouvés jusqu'à la prochaine indexation. Détails et pièges :
[INDEX_RAG.md](https://github.com/amineutron/lyra/blob/main/docs/dev/INDEX_RAG.md).

**La description de chaque outil est ce que la recherche compare à la phrase de l'utilisateur.**
Pour un outil sans exemples dédiés, le document indexé se résume à son nom, sa signature (tirée
de son `inputSchema`) et sa description. Une description en français, qui dit ce que fait l'outil
avec les mots qu'on emploierait pour le demander, fait la différence.

## 3. Ce qui est confirmé avant d'agir

| Outil | Comportement |
|---|---|
| inconnu de Lyra (cas d'un nouveau serveur) | demande de confirmation, Entrée vaut oui ; exécuté sans question avec `lyra -y` |
| nom présent dans `DANGEROUS_TOOLS` | confirmation explicite (« o » ou « oui ») exigée, **jamais** automatique, même avec `-y` |
| nom présent dans `PERFORMANCE_TOOLS` | sans confirmation en mode performance (`lyra -p`) |

Les deux listes sont dans
[`lyra/core/constants.py`](https://github.com/amineutron/lyra/blob/main/lyra/core/constants.py).
`DANGEROUS_TOOLS` se compare au nom court de l'outil (sans préfixe) : un outil nommé `delete` ou
`vm_stop` y est déjà, quel que soit son serveur.

!!! warning "Outil destructif d'un nouveau serveur"
    L'annotation MCP `destructiveHint` qu'un serveur peut poser sur un outil n'est pas encore
    prise en compte par le démon. Pour qu'un outil qui supprime, arrête ou écrase exige une
    confirmation stricte, ajouter son nom à `DANGEROUS_TOOLS`.

Les règles déterministes de Lyra (réponse immédiate sans modèle pour les demandes fréquentes)
ne concernent que les serveurs fournis. Un nouveau serveur passe par la recherche d'outils puis
le modèle ; à formulation égale, une règle existante peut capter la phrase la première (par
exemple « arrête… » pour une VM).

## 4. Le proposer dans l'installeur

Pour qu'il apparaisse dans le menu de l'installeur (case à cocher, champs à saisir, secrets
rangés à part), une entrée dans `installer/core/catalog.yaml` suffit. Champs obligatoires :
`id` (qui devient la clé sous `mcp.servers`), `name`, `short_desc`, `long_desc`, `runtime`
(`python`, `node` ou `none`) et `repo` (sauf `runtime: none`). Le bloc `server` est recopié tel
quel dans `config.yaml` ; sans lui, le démon ne connaîtra pas le serveur.

<!-- inclure: installer/README.md#Ajouter un MCP au catalogue sans-titre -->
