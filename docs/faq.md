# Questions fréquentes

## Faut-il une carte graphique ?

Non. Les modèles par défaut (`qwen2.5-coder:0.5b` et `llama3.2:1b`) tournent sur le
processeur. Une carte NVIDIA de 4 Go accélère la reconnaissance vocale et les modèles. On peut
aussi utiliser un Ollama installé sur une autre machine du réseau : option `--ollama-host` de
l'installeur, ou variable `OLLAMA_HOST`. Détails : [Matériel](materiel.md).

## Qu'est-ce qui sort de la machine ?

Par défaut, rien qui ne soit listé. Chaque flux (téléchargement de modèles à l'installation,
appareils du réseau local pilotés par les serveurs MCP, intégrations optionnelles) est décrit
dans [Flux de données](user/DATA_FLOWS.md), avec la façon de le vérifier soi-même.

## Lyra peut-elle agir sans moi ?

Pas sur ce qui compte. Toute action sensible (machines virtuelles, sauvegardes, suppression)
attend une confirmation, et les outils classés dangereux ne sont jamais confirmés
automatiquement. Le mode performance (`lyra -p`) ne retire la confirmation que pour une liste
fermée d'actions domestiques (lumières, télévision, ampli), jamais pour une VM ou une sauvegarde.
Voir [Ce que le code garantit](securite.md).

## Faut-il parler, ou peut-on écrire ?

Les deux. `lyra` ouvre le mode texte ; `lyra --vocal` active micro et voix. Le mode texte ne
demande ni micro ni sortie son, ni les modèles vocaux.

## Lyra comprend-elle l'anglais ?

L'interface et les règles de détection sont écrites pour le français. La traduction du moteur
de règles est suivie dans une [issue](https://github.com/amineutron/lyra/issues/26), reportée
pour l'instant.

## Sur quels systèmes l'installeur est-il testé ?

Fedora, Ubuntu et Arch, dans des VM propres sans carte graphique (Ollama distant). Le protocole et les
résultats datés sont dans [Installation testée en VM](user/VM_INSTALL_TESTS.md).

## Et sans Internet, ou derrière un proxy ?

L'installeur respecte `HTTPS_PROXY`, `PIP_INDEX_URL`, `HF_ENDPOINT` et `OLLAMA_HOST`, y compris
pour `sudo` et le service Ollama. Pour une machine coupée du réseau, une archive préparée sur une
machine connectée contient modèles, voix et paquets Python. Voir
[Derrière un proxy, sans Internet](reseau.md).

## Faut-il installer tous les serveurs MCP ?

Non. Le cœur fonctionne sans aucun serveur MCP ; chacun se coche à l'installation. Pour piloter
ses propres outils : [Ajouter un serveur MCP](ajouter-un-mcp.md).

## Comment effacer ce que Lyra a gardé ?

`lyra --purge` efface l'historique, les retours et les journaux d'erreurs, puis vérifie que
c'est fait. `lyra --purge --dry-run` liste ce qui serait effacé sans rien toucher.

## Quelle licence ?

AGPL-3.0 : usage, étude, modification et redistribution libres, à condition de publier ses
modifications sous la même licence, y compris pour un service accessible par le réseau. Pour
intégrer Lyra dans un produit fermé ou obtenir un support contractuel, une
[licence commerciale](https://github.com/amineutron/lyra/blob/main/COMMERCIAL-LICENSE.md) est
proposée.
