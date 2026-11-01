# ADR-002 — Petits modèles par défaut, règles d'abord

## Contexte

Lyra doit répondre en quelques secondes sur une machine modeste : environ 4 Go de mémoire
graphique pour tout le système, ou le processeur seul. Or la plupart des demandes sont
répétitives (« démarre la VM x », « allume la télé ») et n'ont pas besoin d'un modèle.

## Décision

- **Règles déterministes d'abord.** [`lyra/core/fastpath.py`](../../lyra/core/fastpath.py)
  normalise la phrase puis interroge [`lyra/rules/`](../../lyra/rules/) (une famille par domaine :
  VM, sauvegardes, Hue, TV, ampli, Chromecast, suivi, Iron Man ; la première qui reconnaît la
  phrase l'emporte). Une règle qui reconnaît la demande produit directement l'appel d'outil : ni
  recherche, ni modèle. 73 des 88 outils fournis ont une règle ; les autres passent volontairement
  par le modèle.
- **Petits modèles sinon.** `qwen2.5-coder:0.5b` (EPHAISTOS, analyse et arguments) et
  `llama3.2:1b` (LYRA, dialogue) par défaut
  ([`installer/core/sources.py`](../../installer/core/sources.py)) ; les modèles 7b et 3b restent
  commentés dans `config.yaml.example`.
- Le très petit modèle est une contrainte de conception, compensée par une boucle d'amélioration
  mesurée des prompts ([article](../articles/2026-09-boucle-ephaistos.fr.md)).

## Mesures

Toutes sur RTX 3080 Ti, septembre 2026 ([Benchmarks](../mesures.md)) :

| Mesure | Résultat |
|---|---|
| Règles seules, 152 requêtes | 152/152, sans modèle |
| Phrases que les règles manquent, configuration finale | `qwen2.5-coder:0.5b` 21/21 en 88 s ; `qwen2.5-coder:7b` 19/21 en 398 s |
| Jeu tenu à l'écart (jamais itéré), 50 formulations | 42/50 (84 %) ; deux jeux scellés précédents : 41/50 et 35/50 |
| Démon chaud, première requête confirmée | 1,6 s (13,3 s avant le démon) |

## Alternatives

- **Modèle 7b par défaut** : moins bon sur les phrases manquées une fois la boucle passée (19/21
  contre 21/21), environ 4,5 fois plus lent, et hors des 4 Go visés.
- **Tout par le modèle** : 0,5b seul extrayait mal les arguments domotiques (février 2026), d'où
  l'ajout des règles TV, ampli et Chromecast.

## Conséquences

- Environ une formulation inédite sur six est mal comprise (mesure du jeu tenu à l'écart).
- Une phrase composée ne garde qu'une action.
- Chaque nouveau domaine gagne à avoir ses règles ; sans elles, il dépend de la description de
  ses outils ([Ajouter un serveur MCP](../ajouter-un-mcp.md)).
