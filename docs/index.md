# Lyra

Assistant DevOps vocal **local par défaut**. On lui parle ou on lui écrit en français ; il
pilote des machines virtuelles, des sauvegardes et des appareils au travers de serveurs
MCP, et ne lance jamais une action sensible sans confirmation humaine.

*English: Lyra is a voice-driven DevOps assistant that runs locally by default (Ollama,
faster-whisper, Piper). It drives VMs, backups and devices through MCP servers and never
runs a sensitive action without a human confirmation. AGPL-3.0, commercial licence
available. Data flows: [English version](user/DATA_FLOWS.en.md).*

## Pourquoi local

- **Rien ne sort sans configuration explicite.** Modèles de langage, reconnaissance et
  synthèse vocales tournent sur la machine. Les sorties réseau possibles sont
  [listées une par une](user/DATA_FLOWS.md), avec la commande qui le vérifie.
- **Pas de facture à l'usage.** Les modèles par défaut (0,5 et 1 milliard de paramètres)
  tiennent dans 4 Go de mémoire graphique, ou tournent sur le processeur, ou sur un Ollama
  partagé du réseau interne.
- **Fonctionne derrière un proxy et sans Internet.** Miroirs internes PyPI et Hugging Face,
  archive d'installation hors ligne : voir [Derrière un proxy, sans Internet](reseau.md).
- **Garanties lisibles dans le code.** Confirmation humaine, validation des arguments,
  règles sudo script par script : chaque garantie renvoie au code et au test qui la tient
  ([Sécurité](securite.md)).

## Ce que Lyra sait faire

<!-- inclure: README.md#Fonctionnalités sans-titre -->

Le cœur (dialogue, recherche d'outils, démon, mode texte) fonctionne sans aucun serveur
MCP ; chacun s'ajoute à l'installation ou ensuite. Pour brancher sa propre infrastructure :
[Ajouter un serveur MCP](ajouter-un-mcp.md).

## Comment ça marche

<!-- inclure: README.md#Architecture sans-titre -->

## Par où commencer

| Je veux… | Page |
|---|---|
| savoir si ma machine suffit | [Matériel](materiel.md) |
| essayer sans rien installer chez moi | [Essayer sans rien installer](essayer.md) |
| installer | [Installation](installation.md) |
| comprendre ce qui est capté et ce qui sort | [Flux de données](user/DATA_FLOWS.md) |
| piloter mes propres outils | [Ajouter un serveur MCP](ajouter-un-mcp.md) |
| voir les mesures | [Benchmarks](mesures.md) |
