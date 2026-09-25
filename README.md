# Policy Observability & Failure Attribution — code for the merged ICLR 2027 paper

Code behind *"When Is a Policy Violation a Model Failure? Policy Observability and Failure
Attribution in Agent-Safety Evaluation."* This repository merges the three study
codebases and the decision-invariance experiment that the paper draws on.

## Layout
- `instruments/authentigrant/` — **authorization** study (who is genuinely authorized to
  instruct an agent). Five-factor grid, executable oracle, deterministic pre-execution gate.
- `instruments/compositionalharmbench/` — **composition** study (can individually safe
  actions combine into an unsafe outcome). 1,920-item factorial, local vs trajectory oracles.
- `instruments/scaffoldrankbench/` — **model-vs-system** study (is security a property of the
  model or the surrounding scaffold). Model × protocol grid, proposed vs realized actions.
- `decision_invariance/` — the **P1 invariance** experiment: extracts retail tool-call
  proposals, renders R/C/K key-order arms, runs the decision screen, and computes excess
  disagreement over repeat noise. `decision_invariance/lib/` vendors the shipped renderer
  and transport constants the scripts import.

Each `instruments/*` subdirectory is a self-contained study with its own README,
`run_experiment.py`, benchmark, results, tests, and dataset card.

## Quickstart — decision-invariance experiment
```bash
cd decision_invariance
pip install -r requirements.txt
# tau2-bench-verified supplies the retail trajectories; point TAU2_ROOT at a clone
export TAU2_ROOT=/path/to/tau2-bench-verified            # pip install -e "$TAU2_ROOT"
python3 scripts/build_cohort.py         # deterministic cohort, 0 model calls
python3 scripts/prepare_schedule.py     # render R/C/K arms, 0 model calls
python3 scripts/run_decision_screen.py --model claude-haiku --workers 6
python3 scripts/analyze_invariance.py   # excess disagreement
```

## Provenance
Every number in the paper traces to a `results/*.json` in one of these subtrees. The
benchmark audits and the decision-invariance cohort make zero model calls; only the
decision-screen stage calls a model (Claude Haiku primary, Sonnet robustness). See each
study's README and the paper's appendices for details.

## License
MIT for code; data are licensed per their upstream terms (see each `DATA_LICENSE` /
`DATASET_CARD.md`).
