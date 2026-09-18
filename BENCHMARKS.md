# Mesures

Tableau genere par `scripts/gen_benchmarks_md.py` depuis les resultats de
`benchmarks/results/`. Ne pas editer a la main : relancer `make bench`.

Protocole, materiel et format : [`benchmarks/README.md`](benchmarks/README.md).

## Latence du pipeline

Mesure du 2026-09-17 sur NVIDIA GeForce RTX 3080 Ti, Python 3.12.13, commit `35bd75c` ([source](benchmarks/results/2026-09-17-rtx-3080-ti-daemon.json)).

| Scenario | Avant | Apres | Gain |
|---|---:|---:|---:|
| One-shot, chemin rapide (regle, sans LLM) | 4.49 s | 3.65 s | 1.2x |
| One-shot, pipeline complet | 17.08 s | 12.31 s | 1.4x |
| REPL : lancement jusqu'au prompt | 20.00 s | 0.26 s | 76.3x |
| REPL : premiere requete confirmee | 13.30 s | 1.60 s | 8.3x |

Ligne de reference : [`baseline-daemon-2026-08-07.json`](benchmarks/baseline-daemon-2026-08-07.json) (avant le chantier demon).

## Detection des commandes (152 requetes, sans LLM)

Mesure du 2026-09-17 ([source](benchmarks/results/2026-09-17-rtx-3080-ti-regles.json)).

**152/152 PASS (100.0 %)** — le moteur de regles seul, sans appel a un modele : resultat deterministe.

| Categorie | Cas | PASS |
|---|---:|---:|
| BACKUP | 35 | 35 |
| DENON | 16 | 16 |
| EDGE | 13 | 13 |
| FEDORA | 63 | 63 |
| HUE | 12 | 12 |
| TV | 13 | 13 |

## Comparaison des modeles (requetes non couvertes par les regles)

21 requetes RULE_MISS passees a EPHAISTOS, mesurees le 2026-09-17 sur NVIDIA GeForce RTX 3080 Ti. Ce banc ne couvre que pylips-mcp, catt-mcp et hue-mcp ; fedora-agents et denon-mcp sont mesures par le banc de regles.

### Configuration de reference

Sans variante : le comportement du depot tel quel.

| Modele EPHAISTOS | Cas | Reussis | Taux | Duree |
|---|---:|---:|---:|---:|
| `llama3.2:1b` | 21 | 8 | 38 % | 395 s |
| `llama3.2:3b` | 21 | 6 | 29 % | 495 s |
| `qwen2.5-coder:0.5b` | 21 | 5 | 24 % | 66 s |
| `qwen2.5-coder:7b` | 21 | 6 | 29 % | 736 s |

| Serveur | Commandes | `llama3.2:1b` | `llama3.2:3b` | `qwen2.5-coder:0.5b` | `qwen2.5-coder:7b` |
|---|---:|---:|---:|---:|---:|
| catt-mcp | 7 | 3/7 | 3/7 | 3/7 | 4/7 |
| hue-mcp | 5 | 2/5 | 2/5 | 1/5 | 0/5 |
| pylips-mcp | 9 | 3/9 | 1/9 | 1/9 | 2/9 |

Sources : [`2026-09-17-rtx-3080-ti-llama3.2-1b-modeles.json`](benchmarks/results/2026-09-17-rtx-3080-ti-llama3.2-1b-modeles.json), [`2026-09-17-rtx-3080-ti-llama3.2-3b-modeles.json`](benchmarks/results/2026-09-17-rtx-3080-ti-llama3.2-3b-modeles.json), [`2026-09-17-rtx-3080-ti-qwen2.5-coder-0.5b-modeles.json`](benchmarks/results/2026-09-17-rtx-3080-ti-qwen2.5-coder-0.5b-modeles.json), [`2026-09-17-rtx-3080-ti-qwen2.5-coder-7b-modeles.json`](benchmarks/results/2026-09-17-rtx-3080-ti-qwen2.5-coder-7b-modeles.json)

### Avec les variantes retenues par la boucle

`LYRA_EXP` = `carte_mots`, `exemple_par_spec`, `exemple_proche`, `exemples_cibles`, `lexical`, `poids_rares`, `recall8`, `signature`, `top3_direct`. Le score accepte les equivalences declarees du banc.

| Modele EPHAISTOS | Cas | Reussis | Taux | Duree |
|---|---:|---:|---:|---:|
| `llama3.2:1b` | 21 | 18 | 86 % | 208 s |
| `llama3.2:3b` | 21 | 18 | 86 % | 185 s |
| `qwen2.5-coder:0.5b` | 21 | 21 | 100 % | 59 s |
| `qwen2.5-coder:7b` | 21 | 19 | 90 % | 398 s |

| Serveur | Commandes | `llama3.2:1b` | `llama3.2:3b` | `qwen2.5-coder:0.5b` | `qwen2.5-coder:7b` |
|---|---:|---:|---:|---:|---:|
| catt-mcp | 7 | 6/7 | 6/7 | 7/7 | 6/7 |
| hue-mcp | 5 | 5/5 | 5/5 | 5/5 | 5/5 |
| pylips-mcp | 9 | 7/9 | 7/9 | 9/9 | 8/9 |

Sources : [`2026-09-17-rtx-3080-ti-llama3.2-1b-exp-modeles.json`](benchmarks/results/2026-09-17-rtx-3080-ti-llama3.2-1b-exp-modeles.json), [`2026-09-17-rtx-3080-ti-llama3.2-3b-exp-modeles.json`](benchmarks/results/2026-09-17-rtx-3080-ti-llama3.2-3b-exp-modeles.json), [`2026-09-17-rtx-3080-ti-qwen2.5-coder-0.5b-exp-modeles.json`](benchmarks/results/2026-09-17-rtx-3080-ti-qwen2.5-coder-0.5b-exp-modeles.json), [`2026-09-17-rtx-3080-ti-qwen2.5-coder-7b-exp-modeles.json`](benchmarks/results/2026-09-17-rtx-3080-ti-qwen2.5-coder-7b-exp-modeles.json)

### Jeu « hors regles » (formulations inedites)

51 formulations inedites sur les 5 serveurs (`tests/cases_hors_regles.py`), tenues a l'ecart des regles et des paraphrases indexees : la mesure de generalisation. `LYRA_EXP` = `arguments_contradictoires`, `carte_equipements`, `carte_mots`, `exemple_par_spec`, `exemple_proche`, `exemples_cibles`, `expansion`, `lexical`, `lexique`, `mots_relatifs`, `poids_rares`, `recall8`, `resolution_arguments`, `signature`, `signature_complete`, `top3_direct`, `verbes_catt`.

| Modele EPHAISTOS | Cas | Reussis | Taux | Duree |
|---|---:|---:|---:|---:|
| `llama3.2:1b` | 51 | 23 | 45 % | 1487 s |
| `llama3.2:3b` | 51 | 32 | 63 % | 595 s |
| `qwen2.5-coder:0.5b` | 51 | 26 | 51 % | 171 s |
| `qwen2.5-coder:7b` | 51 | 36 | 71 % | 1138 s |

| Serveur | Commandes | `llama3.2:1b` | `llama3.2:3b` | `qwen2.5-coder:0.5b` | `qwen2.5-coder:7b` |
|---|---:|---:|---:|---:|---:|
| catt-mcp | 10 | 3/10 | 5/10 | 5/10 | 8/10 |
| denon-mcp | 10 | 7/10 | 8/10 | 7/10 | 6/10 |
| fedora-agents | 11 | 4/11 | 6/11 | 3/11 | 8/11 |
| hue-mcp | 10 | 6/10 | 6/10 | 5/10 | 5/10 |
| pylips-mcp | 10 | 3/10 | 7/10 | 6/10 | 9/10 |

Sources : [`2026-09-18-rtx-3080-ti-llama3.2-1b-exp-horsregles-modeles.json`](benchmarks/results/2026-09-18-rtx-3080-ti-llama3.2-1b-exp-horsregles-modeles.json), [`2026-09-18-rtx-3080-ti-llama3.2-3b-exp-horsregles-modeles.json`](benchmarks/results/2026-09-18-rtx-3080-ti-llama3.2-3b-exp-horsregles-modeles.json), [`2026-09-18-rtx-3080-ti-qwen2.5-coder-0.5b-exp-horsregles-modeles.json`](benchmarks/results/2026-09-18-rtx-3080-ti-qwen2.5-coder-0.5b-exp-horsregles-modeles.json), [`2026-09-18-rtx-3080-ti-qwen2.5-coder-7b-exp-horsregles-modeles.json`](benchmarks/results/2026-09-18-rtx-3080-ti-qwen2.5-coder-7b-exp-horsregles-modeles.json)

## Boucle d'amelioration (variantes LYRA_EXP, inactives par defaut)

Modele mesure : `qwen2.5-coder:0.5b`, graine `42`. Le score strict ignore la table d'equivalences du banc (comparable entre iterations).

| Iteration | Configurations | Meilleure configuration | Score | Strict |
|---:|---:|---|---:|---:|
| 1 | 17 | `exemples_cibles+dedup` | 9/21 | = |
| 1 | 6 | `exemples_cibles+lexical+recall8+carte_mots+top3_direct+exemple_par_spec+poids_rares+exemple_proche+signature+carte_equipements+mots_relatifs+expansion+lexique` | 14/51 | 14 |
| 2 | 17 | `exemples_cibles+lexical+recall8+carte_mots+top3_direct+indice_url` | 14/21 | = |
| 2 | 6 | `exemples_cibles+lexical+recall8+carte_mots+top3_direct+exemple_par_spec+poids_rares+exemple_proche+signature+carte_equipements+mots_relatifs+expansion+lexique+exemple_description+signature_complete+resolution_arguments+carte_son` | 21/51 | 21 |
| 3 | 12 | `exemples_cibles+lexical+recall8+carte_mots+top3_direct+indice_url+exemple_par_spec+poids_rares` | 18/21 | 14 |
| 3 | 7 | `exemples_cibles+lexical+recall8+carte_mots+top3_direct+exemple_par_spec+poids_rares+exemple_proche+signature+carte_equipements+mots_relatifs+expansion+lexique+resolution_arguments+signature_complete+verbes_catt` | 26/51 | 26 |
| 4 | 12 | `exemples_cibles+lexical+recall8+carte_mots+top3_direct+indice_url+exemple_par_spec+poids_rares+exemple_proche+signature` | 20/21 | 16 |
| 4 | 4 | `exemples_cibles+lexical+recall8+carte_mots+top3_direct+exemple_par_spec+poids_rares+exemple_proche+signature+carte_equipements+mots_relatifs+expansion+lexique+resolution_arguments+signature_complete+verbes_catt+nom_de_vm` | 26/51 | 26 |
| 5 | 3 | `exemples_cibles+lexical+recall8+carte_mots+top3_direct+exemple_par_spec+poids_rares+exemple_proche+signature` | 21/21 | 18 |

Sources : [`2026-09-17-rtx-3080-ti-qwen2.5-coder-0.5b-it1-boucle.json`](benchmarks/results/2026-09-17-rtx-3080-ti-qwen2.5-coder-0.5b-it1-boucle.json), [`2026-09-18-rtx-3080-ti-qwen2.5-coder-0.5b-it1-horsregles-boucle.json`](benchmarks/results/2026-09-18-rtx-3080-ti-qwen2.5-coder-0.5b-it1-horsregles-boucle.json), [`2026-09-17-rtx-3080-ti-qwen2.5-coder-0.5b-it2-boucle.json`](benchmarks/results/2026-09-17-rtx-3080-ti-qwen2.5-coder-0.5b-it2-boucle.json), [`2026-09-18-rtx-3080-ti-qwen2.5-coder-0.5b-it2-horsregles-boucle.json`](benchmarks/results/2026-09-18-rtx-3080-ti-qwen2.5-coder-0.5b-it2-horsregles-boucle.json), [`2026-09-17-rtx-3080-ti-qwen2.5-coder-0.5b-it3-boucle.json`](benchmarks/results/2026-09-17-rtx-3080-ti-qwen2.5-coder-0.5b-it3-boucle.json), [`2026-09-18-rtx-3080-ti-qwen2.5-coder-0.5b-it3-horsregles-boucle.json`](benchmarks/results/2026-09-18-rtx-3080-ti-qwen2.5-coder-0.5b-it3-horsregles-boucle.json), [`2026-09-17-rtx-3080-ti-qwen2.5-coder-0.5b-it4-boucle.json`](benchmarks/results/2026-09-17-rtx-3080-ti-qwen2.5-coder-0.5b-it4-boucle.json), [`2026-09-18-rtx-3080-ti-qwen2.5-coder-0.5b-it4-horsregles-boucle.json`](benchmarks/results/2026-09-18-rtx-3080-ti-qwen2.5-coder-0.5b-it4-horsregles-boucle.json), [`2026-09-17-rtx-3080-ti-qwen2.5-coder-0.5b-it5-boucle.json`](benchmarks/results/2026-09-17-rtx-3080-ti-qwen2.5-coder-0.5b-it5-boucle.json)
