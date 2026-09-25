#!/usr/bin/env python3
"""Render recorded controlled-study rates; vendor into each repository's scripts/."""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import paper_style
import matplotlib.pyplot as plt

LABELS = {
    "minimal": "Minimal instruction", "caution": "Generic caution", "checklist": "Recovery checklist", "paraphrase": "Checklist paraphrase",
    "direct_one": "Direct: one transaction", "tools_one": "Tool batch: one transaction", "direct_retry": "Direct: observed retry", "tools_retry": "Tool batch: observed retry",
    "short": "Audited record only", "duplicate_first": "Literal duplicate", "history_first": "History / current first", "history_last": "History / current last",
    "neutral_first": "Neutral / current first", "neutral_last": "Neutral / current last", "contradiction_first": "Conflict / current first", "contradiction_last": "Conflict / current last",
    "valid_named": "Identified / design named", "valid_unnamed": "Identified / name omitted", "invalid_named": "Unidentified / design named", "invalid_unnamed": "Unidentified / name omitted",
    "dynamics_caution": "Equations / caution", "dynamics_ledger": "Equations / ledger", "sums_caution": "Path sums / caution", "sums_ledger": "Path sums / ledger",
    "caution_neutral": "Caution / neutral request", "caution_claim": "Caution / authority claim", "ledger_neutral": "Ledger / neutral request", "ledger_claim": "Ledger / authority claim",
    "local_safe": "Local view / safe", "local_unsafe": "Local view / unsafe", "history_safe": "History / safe", "history_unsafe": "History / unsafe",
    "state_safe": "Current state / safe", "state_unsafe": "Current state / unsafe",
    "reconsider": "Reconsideration", "observe": "Observed-state loop", "ledger": "Provenance reminder", "validate": "Validation prompt",
    "chronological_commit": "Chronological / prior answer", "reverse_commit": "Reverse / prior answer", "chronological_ack": "Chronological / acknowledgement",
    "reverse_ack": "Reverse / acknowledgement", "final_only": "Final snapshot only",
    "explicit_before": "Explicit / update before", "paraphrase_before": "Paraphrase / update before", "explicit_after": "Explicit / update after", "paraphrase_after": "Paraphrase / update after",
}
for policy in [0, 1]:
    for repeat in [0, 1]:
        for opening in [0, 1]:
            LABELS[f"p{policy}-r{repeat}-o{opening}"] = f"Policy {'given' if policy else 'absent'} / {'repeat' if repeat else 'once'} / {'control' if opening else 'decide'}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, default=ROOT / "results/review_openai_v1.json")
    p.add_argument("--metric", default="correct")
    p.add_argument("--label", default="Correct responses (%)")
    args = p.parse_args()
    data = json.loads(args.input.read_text())
    if hasattr(paper_style, "style"):
        paper_style.style()
    else:
        paper_style.apply_style()
    plt.rcParams.update({"font.size": 12, "axes.labelsize": 12, "xtick.labelsize": 11, "ytick.labelsize": 12})
    summary = data["summary"]
    models = sorted(summary)
    conditions = [c for c in LABELS if c in summary[models[0]]]
    conditions += [c for c in summary[models[0]] if c not in conditions]
    fig, ax = plt.subplots(figsize=(7.1, max(2.6, len(conditions) * .38 + .8)))
    figure_values = {"source": args.input.name, "metric": args.metric, "points": []}
    colors = ["#0072B2", "#D55E00"]
    for index, model in enumerate(models):
        y = np.arange(len(conditions)) + (index - (len(models) - 1) / 2) * .2
        points = [summary[model][c][args.metric] for c in conditions]
        x = np.array([r["mean"] * 100 for r in points])
        low = np.array([r["ci95"][0] * 100 for r in points])
        high = np.array([r["ci95"][1] * 100 for r in points])
        ax.errorbar(x, y, xerr=[np.maximum(0, x - low), np.maximum(0, high - x)], fmt="o" if index == 0 else "s",
                    color=colors[index % len(colors)], label={"gpt-5.6-luna": "Luna", "gpt-5.6-sol": "Sol"}.get(model,model.capitalize()), markersize=5, capsize=2, linewidth=1.2)
        for c, value, lo, hi in zip(conditions, x, low, high):
            figure_values["points"].append({"model": model, "condition": c, "label": LABELS.get(c, c),
                                             "percent": float(value), "ci_percent": [float(lo), float(hi)], "printed_percent": round(float(value), 1)})
    ax.set_yticks(np.arange(len(conditions)), [LABELS.get(c, c) for c in conditions], fontsize=11)
    ax.invert_yaxis()
    ax.set_xlim(-2, 103)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xlabel(args.label)
    ax.grid(axis="y", visible=False)
    ax.legend(loc="upper center", bbox_to_anchor=(.5, 1.16), ncol=len(models), fontsize=11)
    fig.tight_layout()
    out = ROOT / "figures"
    out.mkdir(exist_ok=True)
    # Persist every plotted/printed value before rendering the figure.
    (ROOT / "results/review_openai_figure.json").write_text(json.dumps(figure_values, indent=2) + "\n")
    stem = out / "review_openai"
    fig.savefig(stem.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(stem.with_suffix(".png"), dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(stem)


if __name__ == "__main__":
    main()
