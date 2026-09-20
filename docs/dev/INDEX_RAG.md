# Regenerer les index RAG (ordre obligatoire)

Deux collections ChromaDB dans `.chromadb`, l'une derivee de l'autre :

| Collection | Produite par | Contenu |
|---|---|---|
| `lyra_mcp_specs_v2` | `scripts/reindex_mcp_rag_optimized.py` | un document par outil, interroge EN DIRECT aupres des serveurs MCP configures (`config.yaml`), enrichi des paraphrases de `triggers_map` / `examples_map` |
| `lyra_mcp_registry_v3`, `lyra_mcp_capabilities_v3`, `lyra_mcp_parameters_v3` | `scripts/index_rag_3tier.py --clear` | les trois niveaux du RAG 3-tier, derives de la v2 |

Le pipeline de production (`EnhancedPipeline`) lit la v3. Toute modification
de `triggers_map` ou d'un serveur MCP demande donc **les deux** scripts, dans
cet ordre, avec les serveurs domotiques joignables :

```bash
cp -r .chromadb .chromadb.bak-$(date +%Y%m%d)          # 4,5 Mo, on peut revenir en arriere
.venv/bin/python scripts/reindex_mcp_rag_optimized.py   # v2 : interroge les serveurs
.venv/bin/python scripts/index_rag_3tier.py --clear     # v3 : derive de la v2
systemctl --user restart lyra-daemon.service            # le demon garde l'index en memoire
```

Pieges connus :

- `reindex_mcp_rag_optimized.py` fait `clear()` puis reindexe ce que les
  serveurs renvoient : un serveur injoignable a ce moment-la disparait de
  l'index, et un outil intercepte hors MCP (`ironman.run_scene`, ajoute a la
  main en v2) est perdu. `index_rag_3tier.py` ignore les documents sans
  `server_name` pour ne pas creer un serveur fantome.
- Seules les premieres phrases de `triggers_map` sont indexees
  (`LYRA_TRIGGERS_MAX`, `LYRA_VARIANTES_MAX`) : mettre les formulations
  decisives en tete. Jamais une phrase d'un jeu de test
  (`scripts/controle_hors_regles.py --jeu N` le verifie).
- Verifier le resultat sans modele : `scripts/bench_recall.py --jeu hors_regles_2`
  (rang du bon outil, precision du tri net), avant tout banc.
