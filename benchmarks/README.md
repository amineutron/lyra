# Mesures de performance

Chaque chiffre publie sur Lyra doit pouvoir etre rejoue. Ce dossier contient
le protocole, le materiel, et les resultats dates au format JSON.

## Ce qui est mesure

| Banc | Commande | Ce qu'il mesure | Duree |
|---|---|---|---|
| `daemon` | `make bench-daemon` | latence du pipeline : one-shot, demarrage du REPL, premiere requete | ~3 min |
| `regles` | `make bench-regles` | taux de bonne detection des 152 requetes du banc, **sans LLM** | ~5 s |
| `tts` | `make bench-tts` | chargement, latence et RTF de chaque voix Piper | ~2 min |

`make bench` enchaine les trois et regenere [`BENCHMARKS.md`](../BENCHMARKS.md).

## Protocole

Les mesures de latence sont sensibles a la charge de la machine. Une mesure
prise pendant qu'une suite de tests tourne est **sans valeur** : elle mesure la
contention, pas le pipeline.

1. Fermer ce qui consomme CPU ou GPU (tests, builds, conversions video).
   Verifier : `cut -d' ' -f1-3 /proc/loadavg` et `nvidia-smi`.
2. Demarrer le demon et le laisser chaud : `systemctl --user start lyra-daemon`,
   puis envoyer une requete de chauffe. Un demon fraichement demarre charge ses
   index et ses modeles au premier appel ; le mesurer a froid fausse la
   comparaison avec la ligne de reference.
3. Lancer le banc voulu. Chaque execution ecrit un fichier date dans
   `results/`, avec le materiel, les versions et les modeles releves
   automatiquement (`scripts/bench_common.py`).
4. Ne jamais editer un fichier de `results/` a la main : il est la preuve du
   chiffre publie.

## Ligne de reference

`baseline-daemon-2026-08-07.json` contient les mesures **avant** le chantier
demon, quand le pipeline complet (Ollama, ChromaDB, SentenceTransformer,
clients MCP) etait reinitialise a chaque requete. Elles vivaient auparavant en
dur dans `scripts/bench_daemon.py`, ce qui les rendait invisibles et non
comparables.

## Machine de reference

Les resultats de `results/` portent leur propre releve. Celui-ci decrit la
machine sur laquelle les chiffres du README ont ete pris :

| Element | Valeur |
|---|---|
| GPU | NVIDIA GeForce RTX 3080 Ti, 12 Go, pilote 580.159.03 |
| CPU | AMD Ryzen 9 5950X (16 coeurs) |
| RAM | 62 Go |
| Systeme | Fedora, noyau 6.18.x |
| Python | 3.12.13 |
| Ollama | 0.14.1 |

## Modeles

Le pipeline V2 utilise deux petits modeles, choisis pour tenir dans ~4 Go de
VRAM et repondre vite :

| Role | Modele | Temperature |
|---|---|---|
| EPHAISTOS (construit la commande) | `qwen2.5-coder:0.5b` | 0.1 |
| LYRA (dialogue) | `llama3.2:1b` | 0.5 |

Les variantes 7b et 3b restent installables pour comparaison ; le champ
`modeles` de chaque resultat dit ce qui tournait au moment de la mesure.

## Le banc de 152 requetes

`tests/test_campaign_mcp.py` rejoue 152 requetes en francais contre le moteur
de regles seul (`Pipeline._rule_based_detect`) : aucun LLM n'est appele, donc
le resultat est deterministe et comparable d'une machine a l'autre.

| Categorie | Cas |
|---|---|
| FEDORA | 63 |
| BACKUP | 35 |
| DENON | 16 |
| TV | 13 |
| EDGE | 13 |
| HUE | 12 |

Statuts possibles : `PASS` (bon outil, tous les arguments obligatoires),
`PARTIAL` (bon outil, un argument optionnel manque), `FAIL` (mauvais outil ou
argument obligatoire manquant), `RULE_MISS` (aucune regle n'a repondu, la
requete part au LLM).

## Le banc des modeles (21 requetes)

`tests/test_campaign_llm.py --ephaistos <modele> --json` mesure EPHAISTOS sur
21 requetes historiquement non couvertes par les regles (TV 9, HUE 5, CATT 7).

Deux precisions importantes pour lire ces chiffres :

- **Le banc appelle EPHAISTOS directement**, en court-circuitant le moteur de
  regles. C'est volontaire : sans cela il ne mesurerait pas le modele. Les 152
  requetes du banc principal sont toutes absorbees par les regles, et les
  comparer entre modeles donnerait quatre fois 100 % en zero seconde.
- **14 de ces 21 requetes sont aujourd'hui couvertes par les regles** (releve du
  2026-09-17) : les regles ont progresse depuis l'ecriture du banc. Ces chiffres
  disent donc ce que vaut le modele *quand il est sollicite*, pas ce que
  l'utilisateur rencontre au quotidien -- en usage reel, les regles repondent
  avant lui.

### Reproductibilite : fixer la graine

Les modeles ne sont pas deterministes. Sans graine, le meme jeu de 7 requetes
a donne **4, 3 puis 4** bonnes reponses sur trois executions consecutives :
comparer des modeles sur cette base reviendrait a mesurer le bruit autant que
les modeles.

```bash
LYRA_SEED=42 make bench-modeles      # deux executions donnent le meme resultat
```

`LYRA_SEED` n'a d'effet que si elle est definie : rien ne change en production.
Toute comparaison entre modeles publiee ici doit avoir ete prise avec la meme
graine, et la mentionner.

Le banc **refuse de publier** si une panne technique survient (API deplacee,
RAG muet). Le 2026-09-17 il annoncait 0/21 pour le 0.5b : la methode
`_retrieve_specs` avait disparu du pipeline, l'exception etait comptee en
`LLM_FAIL` et le modele etait accuse a tort. Une panne doit interrompre la
mesure, jamais se deguiser en resultat.

## Format d'un resultat

```json
{
  "mesure": "daemon",
  "date": "2026-09-17",
  "materiel": { "gpu": {...}, "cpu": "...", "ram_go": 62 },
  "versions": { "python": "3.12.13", "ollama": "0.14.1", "lyra_commit": "35bd75c" },
  "modeles": { "ephaistos": "qwen2.5-coder:0.5b", "lyra": "llama3.2:1b" },
  "mesures_s": { "...": 0.0 }
}
```

Le nom du fichier suit `<date>-<gpu>[-<variante>]-<mesure>.json`, ce qui permet
de comparer deux machines ou deux dates sans ouvrir les fichiers.
