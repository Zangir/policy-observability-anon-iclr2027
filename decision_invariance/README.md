# Policy Observability & Failure Attribution — audit protocol and instruments

![license](https://img.shields.io/badge/license-MIT-blue) ![calls](https://img.shields.io/badge/audits-0%20model%20calls-green) ![repro](https://img.shields.io/badge/reproducible-laptop-brightgreen)

## News
- Decision-invariance experiment run (Claude Haiku primary, Sonnet robustness):
  candidate-first vs canonical reserialization yields **0.0 excess disagreement** over
  repeat noise. All benchmark audits reproduce from pinned commits with zero model calls.

![teaser figure](../paper/figures/fig1_teaser.png)

**When is a policy violation a model failure?** A reported agent-safety violation is
attributable to a model only when four preconditions hold: **R1** the scored condition is a
function of the agent-visible input, **R2** the pipeline commits to one serialization,
**P1** the decision is invariant to meaning-preserving reserialization, and **A1** the rate
is taken over trials that actually acted. This repository holds the audit protocol, the
decision-invariance experiment, and three executable instruments.

## Headline results
- **ST-WebAgentBench**: all 3,057 policies render (R1-A pass) yet **2,281 / 3,057 = 74.6%**
  scored conditions are absent from the agent-visible input (R1-B fail). 0 model calls.
- **AuthorityBench**: **34** byte-identical prompt pairs across **21** scenarios carry
  opposite authorization labels; **4,567 / 6,924** scored trials never acted (A1). 0 model calls.
- **tau2-bench retail**: R1-B passes with a residue of 1; R2 fails (agent-visible path
  carries two `json.dumps` conventions).
- **Decision invariance**: on 66 retail proposals under R/C/K key-order arms, candidate-first
  vs canonical shows **excess disagreement 0.0** (Haiku) over repeat noise — reserialization
  does not move the guard's decision beyond its own sampling noise.

## Results
| Benchmark / study | Criterion | Result | Model calls |
|---|---|---|---|
| ST-WebAgentBench | R1-B | 2,281/3,057 (74.6%) scored conditions absent | 0 |
| AuthorityBench | R1-B / A1 | 34 opposite-label pairs / 21 scenarios; 4,567/6,924 idle | 0 |
| tau2-bench retail | R1-B / R2 | pass (residue 1) / fail (two serializations) | 0 |
| Decision invariance (Haiku) | P1 | excess disagreement 0.0 [0.0, 0.0] | 396 |

## Smoke test
```bash
# ~1 min, no model calls: rebuild cohort + arms and verify R/C/K are byte-distinct
python3 scripts/build_cohort.py && python3 scripts/prepare_schedule.py
```

## Quickstart
```bash
# 1. cohort (deterministic, 0 model calls) from pinned tau2 retail trajectories
python3 scripts/build_cohort.py
# 2. render R/C/K arms + schedule (0 model calls)
python3 scripts/prepare_schedule.py
# 3. decision-screen calls (claude CLI; resumable)
python3 scripts/run_decision_screen.py --model claude-haiku --workers 6
# 4. analyze excess disagreement
python3 scripts/analyze_invariance.py
# 5. figures
python3 scripts/make_figures.py
```

## Layout
- `scripts/build_cohort.py` — extract typed retail proposals into frozen packets.
- `scripts/prepare_schedule.py` — render R/C/K arms (reuses shipped `render.py`), build schedule.
- `scripts/run_decision_screen.py` — decision-screen model calls, preserving the shipped
  guard instruction, decision schema, and evidence payload verbatim.
- `scripts/analyze_invariance.py` — excess disagreement (reuses shipped `pair_statistics`).
- `scripts/make_figures.py`, `scripts/paper_style.py` — figures.
- `results/` — all persisted numbers; the paper cites only these.

## Provenance & honesty
Every number in the paper traces to a file under `results/`. The benchmark audits make
zero model calls and reproduce from pinned upstream commits (hashes recorded). The
decision-invariance cohort is extracted deterministically from tau2-bench-verified's shipped
retail trajectories; only the decision-screen stage calls a model. Model families: Claude
Haiku (primary) and Sonnet (robustness). Deviations (macOS transport, cohort extraction,
spend-capped second family) are in `../../logs/deviations.md`.

## Data access
tau2-bench-verified is cloned into `../upstream/` (gitignored), pinned by commit
`864350a8971a8f8ee9e7b8472e2edc380a806b0c` with retail `policy.md` SHA-256
`2c9652afbce57d6e087768d37cda64d31c53d50b3e3225cfdb791bac66466467`.

## If you use this, cite
```bibtex
@inproceedings{anon2027policyobservability,
  title     = {When Is a Policy Violation a Model Failure? Policy Observability and
               Failure Attribution in Agent-Safety Evaluation},
  author    = {Anonymous Authors},
  booktitle = {International Conference on Learning Representations (ICLR)},
  year      = {2027},
  note      = {Under double-blind review}
}
```

## License
MIT (code). See `LICENSE`. Data are read from upstream under their own terms. (pending publication)
