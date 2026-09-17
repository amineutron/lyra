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
