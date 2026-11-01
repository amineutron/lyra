# Installation

Un seul point d'entrée, `./installer/install.sh`, depuis un clone du dépôt. Trois façons
de le suivre, qui exécutent exactement le même parcours :

- en terminal (par défaut) : menu des serveurs MCP à cocher, progression animée ;
- `--app` : installeur graphique local, servi sur `http://127.0.0.1:9877/ui/` ;
- `--headless` : sans interface, chaque question prend sa valeur par défaut (machines sans
  terminal, essais en VM).

`--demo` simule tout le parcours sans exécuter une seule commande.

<!-- inclure: README.md#Démarrage rapide niveau=2 -->

<!-- inclure: installer/README.md#Garanties niveau=2 -->

Réseau d'entreprise, proxy ou machine sans Internet : voir
[Derrière un proxy, sans Internet](reseau.md).
