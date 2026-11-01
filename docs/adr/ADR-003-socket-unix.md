# ADR-003 — Démon sur socket UNIX plutôt qu'une API HTTP

## Contexte

Charger le pipeline (modèles d'embeddings, index, sessions MCP) prenait de 17 à 20 secondes à
chaque commande. Il fallait un processus résident, joignable par plusieurs clients : terminal,
voix, et l'interface web neutroncore au travers de son API.

## Décision

Le démon `lyra-daemon` (service systemd utilisateur) écoute sur `~/.lyra/lyra.sock`
([`lyra/daemon/server.py`](../../lyra/daemon/server.py)) :

- socket UNIX en droits 0600 : seul le compte de l'utilisateur (et root) peut s'y connecter ;
- protocole en lignes JSON, un message par ligne, chacun typé (`request`, `tool`, `analyze`,
  `answer`, `purge`…) ([`lyra/daemon/protocol.py`](../../lyra/daemon/protocol.py)) ;
- une requête du pipeline à la fois (verrou), plusieurs connexions en parallèle ;
- les questions de confirmation partent vers le client (`ask`) et attendent sa réponse 120 s.

Mesures à l'introduction du démon : commande isolée de 17,1 s à 1,3 s, ouverture du mode
interactif de 20 s à 0,25 s.

## Alternatives

- **API HTTP locale** : aucune note ne la discute. Un port local est joignable par toute page
  web ouverte dans le navigateur (requêtes inter-origines, rebinding DNS) et par tous les comptes
  de la machine ; un socket en 0600 ne l'est que par l'utilisateur, sans jeton à gérer.
- **Pas de démon** : le mode `--standalone` reste disponible, au prix du temps de chargement.

## Conséquences

- Aucune authentification des clients au-delà des droits du fichier : tout processus du compte
  de l'utilisateur peut piloter Lyra, y compris déclarer une action déjà confirmée (`confirmed`)
  sur la route `tool`. C'est assumé : un tel processus a déjà les droits de l'utilisateur.
- L'API web (lyra-control-api) traduit HTTP vers ce socket et porte sa propre authentification
  (clé et jeton de confirmation).
- Le service n'a pas de restriction systemd (`NoNewPrivileges` est incompatible avec les scripts
  lancés par sudo, voir [ADR-005](ADR-005-sudoers-par-script.md)).
