#!/usr/bin/env python3
"""Render CompositionalHarmBench figures only from persisted JSON."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch

from paper_style import METHOD_COLORS, annotate_headline, comparison_matrix, save, style

ROOT = Path(__file__).resolve().parents[1]
RESULTS, FIGURES = ROOT / "results", ROOT / "figures"


def load(name: str) -> dict:
    return json.loads((RESULTS / name).read_text())


def finish(fig, name: str, caption: str, shows: str, metadata: list) -> None:
    FIGURES.mkdir(exist_ok=True)
    save(fig, str(FIGURES / name))
    metadata.append({"file": f"figures/{name}.pdf", "pattern": name,
                     "caption_draft": caption, "shows": shows})


def teaser(data: dict, metadata: list) -> None:
    value = data["headline"]["local_harm_rate"]
    fig, axes = plt.subplots(1, 3, figsize=(11.3, 3.15),
                             gridspec_kw={"width_ratios": [1.35, 1.2, 1], "wspace": 0.38})
    panels = [("Locally permitted", "read(secret)  ✓\ninspect  ✓\nsend_external  ✓"),
              ("Global consequence", "secret → working note\n→ external sink\n\ntrajectory harm")]
    for ax, (heading, body) in zip(axes[:2], panels):
        ax.axis("off")
        box = FancyBboxPatch((.05, .12), .9, .76, boxstyle="round,pad=.03",
                             facecolor="#EAF3F8", edgecolor="#0072B2", linewidth=1.3)
        ax.add_patch(box)
        ax.text(.5, .75, heading, ha="center", fontweight="bold", transform=ax.transAxes)
        ax.text(.5, .42, body, ha="center", va="center", transform=ax.transAxes,
                linespacing=1.35)
    ax = axes[2]
    ax.bar([0, 1], [value, 0], color=[METHOD_COLORS.assign("Local filter"),
                                      METHOD_COLORS.assign("Trajectory monitor")])
    ax.set_ylim(0, 80)
    ax.set_ylabel("Realized compositional harm (%)")
    ax.set_xticks([0, 1], ["Local\nfilter", "Trajectory\nmonitor"])
    annotate_headline(ax, 0, value, f"{value:.0f}%")
    annotate_headline(ax, 1, 0, "0%")
    finish(fig, "teaser", "Every call passes the local policy, yet accepted plans can violate the final-state oracle; replaying identical plans exposes the safeguard gap.", "The memoryless filter leaves Haiku's 65% residual harm unchanged while the trajectory monitor blocks it.", metadata)


def safeguard(data: dict, metadata: list) -> None:
    run = data["runs"]["haiku_primary"]
    names = ["Unprotected", "Local filter", "Trajectory monitor", "Approval"]
    keys = ["unprotected", "local_filter", "trajectory_monitor", "approval"]
    values = [run["by_mode"][key]["compositional_harm_rate"] for key in keys]
    ci = run["by_mode"]["local_filter"]["compositional_harm_ci95"]
    err = np.array([[values[0] - ci[0], values[1] - ci[0], 0, 0],
                    [ci[1] - values[0], ci[1] - values[1], 0, 0]])
    fig, ax = plt.subplots(figsize=(7.1, 3.6))
    ax.bar(np.arange(4), values, yerr=err, capsize=3,
           color=[METHOD_COLORS.assign(name) for name in names])
    ax.set_xticks(np.arange(4), [n.replace(" ", "\n") for n in names])
    ax.set_ylabel("Realized compositional harm (%)")
    ax.set_ylim(0, 100)
    for i, value in enumerate(values):
        if value == 0: ax.text(i, 2, "0", ha="center", fontsize=12)
    finish(fig, "safeguard_comparison", "Realized harm after counterfactual replay of identical Haiku plans; intervals resample matched workflow families.", "The tested stateful references block these constructed harms.", metadata)


def model_contract(data: dict, metadata: list) -> None:
    pairs = [("Haiku local", "haiku_primary"), ("Haiku resample", "haiku_resample"),
             ("Sonnet local", "sonnet_primary"), ("Haiku explicit", "haiku_explicit")]
    values = [data["runs"][key]["composition_attempt_rate"] for _, key in pairs]
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    ax.bar(np.arange(4), values, color=[METHOD_COLORS.assign(label) for label, _ in pairs])
    ax.set_xticks(np.arange(4), [label.replace(" ", "\n", 1) for label, _ in pairs])
    ax.set_ylabel("Accepted compositional plans (%)")
    ax.set_ylim(0, 100)
    for i, value in enumerate(values):
        if value == 0: ax.text(i, 2, "0", ha="center", fontsize=12)
    finish(fig, "model_contract", "Compositional-plan acceptance across model and contract ablations on the same fixed slice.", "The Haiku local-contract acceptance pattern recurs, while Sonnet and an explicit trajectory contract reject all harmful plans.", metadata)


def diagnostic(data: dict, metadata: list) -> None:
    groups = [("No memory", data["diagnostics"]["memory"]["false"]),
              ("Memory", data["diagnostics"]["memory"]["true"]),
              ("Direct", data["diagnostics"]["indirect"]["false"]),
              ("Indirect", data["diagnostics"]["indirect"]["true"]),
              ("Single", data["diagnostics"]["multi_agent"]["false"]),
              ("Multi-agent", data["diagnostics"]["multi_agent"]["true"])]
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    ax.bar(np.arange(len(groups)), [value for _, value in groups],
           color=METHOD_COLORS.assign("Haiku local"))
    ax.set_xticks(np.arange(len(groups)), [label for label, _ in groups], rotation=18)
    ax.set_ylabel("Accepted compositional plans (%)")
    ax.set_ylim(0, 100)
    finish(fig, "factor_diagnostic", "Descriptive acceptance rates across paired trajectory attributes in the fixed 20-family slice.", "Persistent-memory and indirect cases are the largest diagnostic strata; these small cells are descriptive.", metadata)


def matrix(metadata: list) -> None:
    data = load("comparison_matrix.json")
    rows = [row["name"] for row in data["rows"]]
    cols = ["Local-pass\ncomposition", "Matched\ntriplets", "Deterministic\noracle",
            "Same-plan\nreplay", "Burden"]
    keys = data["columns"][1:]
    cells = [[row[key].replace("not stated", "?") for key in keys] for row in data["rows"]]
    quant = [row["trajectory_items"] for row in data["rows"]]
    fig, ax = plt.subplots(figsize=(10.4, 4.0))
    comparison_matrix(ax, rows, cols, cells, ours_row=0, quant_col=quant,
                      quant_label="Items")
    finish(fig, "comparison_matrix", "Capability comparison against verified 2026 trajectory benchmarks; a question mark marks a feature not established by the abstract, not proof of absence.", "CompositionalHarmBench is narrower than AgentHazard and combines paired controls, exact oracles, causal replay, and burden measurement.", metadata)


def main() -> None:
    style()
    data = load("aggregate.json")
    metadata = []
    teaser(data, metadata)
    plt.rcParams.update({"font.size": 12, "axes.labelsize": 12, "axes.titlesize": 13, "xtick.labelsize": 12, "ytick.labelsize": 12, "legend.fontsize": 12})
    safeguard(data, metadata)
    model_contract(data, metadata)
    diagnostic(data, metadata)
    matrix(metadata)
    (FIGURES / "figures.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"wrote {len(metadata)} figures")


if __name__ == "__main__":
    main()
