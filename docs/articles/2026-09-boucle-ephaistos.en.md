# Getting a 0.5-billion-parameter model to pick the right tool: a measured improvement loop, mechanism before model

*Amine Arouabah (amineutron), September 2026. Working version, not peer reviewed. Code, test sets and raw results: https://github.com/amineutron/lyra (AGPL-3.0). French original: [2026-09-boucle-ephaistos.fr.md](2026-09-boucle-ephaistos.fr.md).*

## Abstract

Lyra is a local voice assistant that drives virtual machines, backups and the home automation of a flat through 88 MCP tools spread over five servers. The component that picks the tool and its arguments (EPHAISTOS) runs on `qwen2.5-coder:0.5b`, an 800 MB model that answers in two to five seconds on a consumer GPU. At the start it found the right tool for none of the 21 requests the hand-written rules did not cover. We describe an improvement loop of 21 iterations, run over four days, whose principle is to measure the mechanism that presents candidates to the model before touching the model or the prompt. Every idea is a switchable variant, measured alone, in pairs and combined, with a fixed seed, against a hypothesis written before the measurement. The score on the initial set goes from 0/21 to 21/21; on five successive development sets, the final configuration reaches 100 %. The number that matters is the one from three sets sealed before any iteration and measured once: 41/50, 35/50 and 42/50, a generalisation between 70 and 85 % on free phrasing never seen before. We show that the levers that generalise are data and mechanical decisions (paraphrases, lexical sort, a tool imposed when the sort is unambiguous, real inventory), that every instruction added to the prompt made the model worse, that model size only mattered once the mechanism was fixed, and that the bench must measure the production path, otherwise it measures something else.

## 1. Context and problem

An assistant that executes commands has to turn a free sentence ("mets staging-03 au repos", put staging-03 to rest) into a precise tool call (`vm_stop(vm_name="staging-03")`) among dozens of candidates. Lyra does it in three steps: deterministic Python rules for frequent phrasings; failing that, a search in an index of the tools (three-tier RAG, ChromaDB, `paraphrase-multilingual-MiniLM` embeddings) that returns candidate specifications; then a language model that picks the tool and fills the arguments. The very small model is a design constraint: local execution, a few seconds of latency, 4 GB of VRAM for the whole system.

The initial problem was simple to state and wrong to diagnose. On a bench of 21 requests not covered by the rules, EPHAISTOS found the right tool 0 times. Three working sessions had concluded that the model was too small and had tuned the prompt, without lasting effect. One clue contradicted that conclusion: a 7-billion-parameter model did no better than a 1-billion one on the same bench. If size changes nothing, the problem is not in the model.

## 2. Method

### 2.1 Principle

The loop applies five rules, in this order.

1. **Hypothesis written before the measurement**, with the expected impact in number of cases. Without a prior hypothesis, a number that moves teaches nothing.
2. **Measure the mechanism before the model.** The rank of the right tool among the candidates shown, and the precision of the criterion that decides to impose a tool, are computed without any model call, in twenty seconds per configuration (`scripts/bench_recall.py`). An idea with no mechanical effect is not sent to the bench.
3. **An idea is a named variant**, switched on by an environment variable (`LYRA_EXP`), implemented by a tested pure function. The bench (`scripts/bench_boucle.py`) measures each variant alone, in pairs, and all together, on top of what previous iterations kept, with a fixed seed (`LYRA_SEED=42`). Without a seed, the same bench varies by plus or minus one case out of seven. Figure 1 shows why pairs are indispensable: a variant can hurt alone and be decisive combined.

![Single versus paired variants, iteration 2](figures/seules_vs_paires_it2.svg)

*Figure 1. Iteration 2 on set 1: the first twelve configurations measured (base, single variants, pairs). Lexical search alone loses one case; combined with the three-spec window it gains four.*

4. **Classify every remaining failure** automatically: was the right tool shown to the model, at what rank; did the model invent a name, pick a neighbour, miss an argument. The raw answer and the exact prompt are kept.
5. **Repeat** until the threshold (99 %) is reached, and record hypotheses and results of every iteration in a public journal (tracking issue).

### 2.2 Test sets

Six sets were written along the loop. The first (21 requests, close to the rules, TV, cast, lights) is the original bench. The second (51 unseen phrasings over the five servers) was written to measure the generalisation of the first; a mechanical control (`scripts/controle_hors_regles.py`) rejects any sentence caught by a rule or copied from an indexed paraphrase. The following sets (100, 50, 50, 50 sentences, everyday register, real machine names) were written under a protocol fixed after set 3: **seal the next set before touching the code, measure it once, never iterate on it**. The day a sealed set is used for an iteration, it loses its status and a new set is sealed.

The score is the number of cases where the chosen tool is the right one (or a declared equivalent, e.g. `cast_youtube` for `youtube_video`) and the mandatory arguments are present. A "strict" score, without equivalences, is published alongside.

### 2.3 Hardware

RTX 3080 Ti (12 GB), ollama, `qwen2.5-coder:0.5b` for EPHAISTOS and `llama3.2:1b` for dialogue. One measurement at a time, idle machine; a campaign launched under load was aborted twice for lack of memory.

## 3. Results

### 3.1 Progression

![Best configuration per iteration](figures/progression.svg)

*Figure 2. Best configuration of each iteration, per development set. Numbers are read from `benchmarks/results/` by `scripts/gen_figures_boucle.py`.*

| Set | Start | Final | Iterations |
|---|---|---|---|
| 1 (21) | 0 (5 after repairing the bench) | 21 | 1 to 5, then 11 to 13 |
| 2 (51) | 13 | 51 | 1 to 11 (set-specific numbering) |
| 3 (100) | 56 (single measurement) | 100 | 14 to 21 |
| 4 (50) | 41 (single measurement) | 50 | 17 to 21 |
| 5 (50) | 35 (single measurement) | 50 | 17 to 21 |
| 6 (50) | **42 (single measurement)** | never iterated | |

### 3.2 What mattered, in chronological order

**The bench itself was broken.** The first job was to make a bench refuse to publish when an API had disappeared: the initial 0/21 counted technical failures as model failures. The real starting point was 5/21.

**The model could not see the right answer.** Measured without the model: the right tool was among the five candidates returned by the index for 8 requests out of 21, in first position for 4. And the model received a single specification on the first attempt. Three causes, all in the mechanism: a 6,100-token system prompt in a 4,096 window; an index stale with respect to the paraphrases written since; an extraction regular expression (`[^E]+?`) unable to cross a capital E, which cost 38 tools out of 88 all their paraphrases.

**Data first.** Regenerating the index with paraphrases for every tool, without duplicates, took the right tool from 8 to 20 times out of 21 among the candidates. The score did not move right away: showing the right answer is not enough for a model of this size.

**One example per specification, taken from its paraphrases.** This is the lever that turned recall into score (iteration 3, 15 then 18/21). A 0.5-billion model imitates an example; it does not follow a rule.

**Every instruction made the model worse.** A keyword routing rule, a reminder "turn off = *_off tool", an instruction about URLs, two examples instead of one: each addition to the prompt lowered the score. The last case of the first bench was won by **removing** a sentence from the prompt.

**When the sort is unambiguous, do not ask the model.** Candidates are re-sorted by word maps ("moins" points to `down`, "sans le son" to `mute`, "le point" to `status`). When the first candidate has at least two points and one more than the next, the tool is imposed and the model only fills the arguments. The precision of this criterion, measured without the model, is 27/27 when introduced and 70/0 (correct / wrong impositions) at the end. This is what took set 2 from 39 to 51/51, where a 1.5-billion model did no better than the 0.5-billion one.

**The levers that generalise do not depend on the sentences.** After the single measurement of set 3 (56/100), three levers written without looking at its failures: the real inventory of machines read at startup (instead of a name pattern), an everyday-language lexicon written domain by domain, the same verbs in the sort maps. Figure 3 gives their full ablation; they stack almost additively (56, 70, then 82 at the next iteration).

![Ablation of the three generic levers](figures/ablation_it14.svg)

*Figure 3. Iteration 14 on set 3: each lever alone, each pair, all three, on top of the 31-variant base.*

**A code defect, not a model one.** At iteration 18, five failures had the right tool in first position with an unambiguous sort, and the model answered something else: the tool imposed by the first pass was put back in play by a second pass. Fixing it gained one point and 30 % fewer model calls (543 s to 381 s for 100 requests).

### 3.3 What a sealed set is worth

![Generalisation](figures/generalisation.svg)

*Figure 4. For each sealed set: single measurement (grey) and score after iteration (green). Only the grey measures generalisation.*

The 21/21 of set 1 and the 51/51 of set 2 measured the loop, not the product: the configuration that scored 72/72 gave 56/100 on set 3 written afterwards. Three sealed sets of 50 sentences, each measured once with configurations one point apart on the development set, gave 41, 35 and 42. We draw two conclusions: the generalisation of this mechanism with a 0.5-billion model sits between 70 and 85 % on free phrasing; and a number over 50 sentences carries several points of uncertainty, which forbids comparing two configurations on a single set of that size.

In real use, between 16 and 24 sentences out of 50 in each set are caught by a rule before any model call.

### 3.4 Model comparison

![Eleven models on set 2](figures/modeles_jeu2.svg)

*Figure 5. Eleven models on set 2, intermediate configuration of 2026-09-18 (17 to 22 variants). The three 7-billion models are beaten by a 3-billion one of the same family.*

At that stage size mattered, in a 23 to 44 range. Once the unambiguous sort and the imposed tool were in place, the 0.5-billion model reached 51/51 on that same set, and the 1.5-billion one did no better at equal configuration. The mechanism made model size secondary.

### 3.5 The bench measured a path the product did not run

A manual acceptance test, twenty sentences spoken to the real system, gave answers unrelated to the bench. The bench called EPHAISTOS directly; the production pipeline sent it a single specification, without its tool name (the model then read the first word of the description as the name), then let a session context and an intent classifier override the result. Once the pipeline was aligned with the bench, and the bench given a mode that goes through the real pipeline (`--reel`), the three development sets give 21/21, 43/43 and 91/92 on the production path, correct refusals (non-existent machines) counted apart. This step should have preceded any published number.

## 4. What did not work

Seventeen variants were measured then removed from the code, their measurements staying in the published results: prompt instructions (routing, on/off, URLs, spec numbering), voting over three candidate orders (a model of this size is not noisy, it is drawn to the same neighbour on every call), fuzzy resolution of an invented name, loosening the unambiguity criterion (the mechanical measurement announced three false positives, the bench lost four points), extending the query with synonyms before the sort (noise won), constrained JSON output, spec deduplication, a second example per spec.

## 5. Limits

A single target model was iterated on; model comparisons are at an intermediate configuration. The sets are written by one person, in French, for one flat: the remaining ambiguities ("allume l'entree": neither a light nor a group of that name on the bridge) reflect that installation. Sealed sets have 50 sentences, which gives a range, not a number. The 99 % threshold was reached on development sets, never on a sealed one. Finally, word maps and lexicons are hand-written: they generalise better than sentences, but remain tied to the domain.

## 6. Conclusion

The model was not the problem. What it was shown was: a stale index, a single specification, no example, a sort that decided nothing, and a production pipeline different from the bench. Every time we tried to help the model with an instruction, it did worse. Every time we fixed what it saw, or decided in its place when the mechanism was sure, it did better. The method that made this visible holds in three gestures: write the hypothesis before the measurement, measure the mechanism without the model, seal the next set before touching the code. The number to publish is never the one from the set you worked on.

## Reproduce

```
git clone https://github.com/amineutron/lyra
LYRA_SEED=42 .venv/bin/python scripts/bench_recall.py --jeu hors_regles_2 --configs "DEFAUT"
LYRA_SEED=42 .venv/bin/python tests/test_campaign_llm.py --ephaistos qwen2.5-coder:0.5b --jeu hors_regles_5 --reel
.venv/bin/python scripts/gen_figures_boucle.py
```

Detailed method: `docs/dev/BOUCLE_AMELIORATION.md`. Dated measurements: `BENCHMARKS.md` and `benchmarks/results/` (75 JSON files). Iteration journal: issue #72 of the tracking repository.
