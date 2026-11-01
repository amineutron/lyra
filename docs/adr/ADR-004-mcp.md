# ADR-004 — MCP comme couche d'outils

## Contexte

Lyra pilote des choses très différentes (VM KVM, sauvegardes, TV, lampes, ampli, Chromecast) et
doit pouvoir en piloter d'autres sans changer son code.

## Décision

Chaque domaine est un serveur [MCP](https://modelcontextprotocol.io/) lancé par le démon et joint
en stdio ([`modules/mcp.py`](../../modules/mcp.py), exécuteur HESTIA dans
[`lyra/hestia/`](../../lyra/hestia/)) :

- déclaration dans `config.yaml` (`mcp.servers.<nom>`) ; outils préfixés par ce nom
  (`tv.power_on`) ;
- session persistante pour un serveur lancé par un chemin absolu ou par Python, processus par
  appel pour un serveur Node ;
- liste des outils lue en direct (`tools/list`), indexée pour la recherche sémantique ;
- catalogue d'installation déclaratif ([`installer/core/catalog.yaml`](../../installer/core/catalog.yaml)) :
  ajouter un serveur ne demande aucun code.

## Alternatives

Aucune note ne discute d'une autre approche : le premier client MCP (pour fedora-agents) date de
la phase 1. Ce qui a joué depuis : les serveurs fournis servent aussi à d'autres clients MCP
(assistants de bureau, éditeurs), et un nouveau domaine s'ajoute par la configuration.

## Conséquences

- Le cœur fonctionne sans aucun serveur ; chacun s'ajoute ou se retire par la configuration.
- Les opérations très longues (clone de VM, sauvegarde) dépassaient le délai d'un appel MCP :
  elles passent par `scripts/async_mcp_wrapper.py`, qui lance directement les scripts système en
  tâche de fond.
- Un serveur MCP tourne avec les droits de l'utilisateur et tout son environnement : installer un
  serveur, c'est lui faire confiance. Ses descriptions d'outils orientent la recherche, et sa
  sortie est lue par le modèle de dialogue. Voir le [modèle de menaces](../THREAT_MODEL.md).
- Un serveur doit vider sa sortie d'erreur : un tube de 64 Ko plein figeait le démon (corrigé,
  [article](../articles/2026-09-tube-stderr.fr.md)).
