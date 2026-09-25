#!/usr/bin/env python3
"""Render ScaffoldRankBench figures from persisted result JSON only."""
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


def finish(fig, name: str, caption: str, shows: str, meta: list) -> None:
    FIGURES.mkdir(exist_ok=True)
    save(fig, str(FIGURES / name))
    meta.append({"file": f"figures/{name}.pdf", "pattern": name,
                 "caption_draft": caption, "shows": shows})


def cellmap(data: dict) -> dict:
    return {(c["model"], c["scaffold"]): c for c in data["cells"]}


def teaser(data: dict, meta: list) -> None:
    """Show how scaffold choice changes harm for otherwise fixed cases."""
    cells = cellmap(data)
    scaffolds = data["scaffolds"]
    values = [
        cells[("haiku", scaffold)]["attack_realized_harm_rate"]
        for scaffold in scaffolds
    ]
    fig, axes = plt.subplots(1, 3, figsize=(11.4, 3.2),
                             gridspec_kw={"width_ratios": [1.2, 1.25, 1.75], "wspace": 0.35})
    for ax, heading, body in [
        (
            axes[0],
            "Same formal case",
            "policy + records\ntools + action budget\nclean / one-defect pair",
        ),
        (
            axes[1],
            "Only scaffold changes",
            "one-shot · ReAct\nplanner–validator\nprovenance ledger",
        ),
    ]:
        ax.axis("off")
        box = FancyBboxPatch((.06, .13), .88, .72, boxstyle="round,pad=.03",
                             facecolor="#EAF3F8", edgecolor="#0072B2", linewidth=1.3)
        ax.add_patch(box)
        ax.text(
            .5, .72, heading, ha="center", fontweight="bold", transform=ax.transAxes
        )
        ax.text(
            .5,
            .40,
            body,
            ha="center",
            va="center",
            transform=ax.transAxes,
            linespacing=1.4,
        )
    ax = axes[2]
    xs = np.arange(4)
    colors = [METHOD_COLORS.assign(s) for s in scaffolds]
    ax.bar(xs, values, color=colors)
    ax.set_xticks(xs, ["One-shot", "ReAct", "Plan +\nvalidate", "Ledger"])
    ax.set_ylabel("Realized attack harm (%)")
    ax.set_ylim(0, max(35, max(values) + 10))
    for x, value in zip(xs, values):
        annotate_headline(ax, x, value, f"{value:g}%")
    finish(
        fig,
        "teaser",
        "ScaffoldRankBench holds each authorization case fixed and changes only "
        "the protocol. Bars show Haiku's realized harm on 16 matched attack families.",
        "A surrounding protocol changes realized security for the same model and "
        "formal cases.",
        meta,
    )


def factorial(data: dict, meta: list) -> None:
    cells = cellmap(data)
    fig, ax = plt.subplots(figsize=(8.2, 4.0))
    xs = np.arange(4)
    width = .24
    for i, model in enumerate(data["models"]):
        values, lo, hi = [], [], []
        for scaffold in data["scaffolds"]:
            cell = cells[(model, scaffold)]
            values.append(cell["attack_realized_harm_rate"])
            lo.append(cell["attack_realized_harm_ci95"][0])
            hi.append(cell["attack_realized_harm_ci95"][1])
        err = np.array([np.array(values) - lo, np.array(hi) - values])
        ax.bar(xs + (i - 1) * width, values, width, yerr=err, capsize=2.5,
               label=model.capitalize(), color={"haiku": "#0072B2", "sonnet": "#D55E00", "opus": "#009E73"}[model])
        for x, value in zip(xs + (i - 1) * width, values):
            if value == 0: ax.text(x, 1, "0", ha="center", va="bottom", fontsize=12)
    ax.set_xticks(xs, ["One-shot", "ReAct", "Planner–validator", "Ledger"])
    ax.set_ylabel("Realized attack harm (%)")
    ax.set_ylim(0, 55)
    ax.legend(ncol=3)
    finish(fig, "factorial_security", "Realized harm across the model-by-scaffold factorial; intervals bootstrap the 16 matched task families.", "Initial scaffold contrasts also change exposed answers and model-call budgets; they do not isolate scaffold reasoning.", meta)


def utility_cost(data: dict, meta: list) -> None:
    cells = cellmap(data)
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.5))
    for model in data["models"]:
        x = [cells[(model, s)]["mean_model_calls"] for s in data["scaffolds"]]
        y = [cells[(model, s)]["clean_completion_rate"] for s in data["scaffolds"]]
        axes[0].plot(x, y, marker="o", label=model.capitalize(), color={"haiku": "#0072B2", "sonnet": "#D55E00", "opus": "#009E73"}[model])
    axes[0].set_xlabel("Mean model calls per item")
    axes[0].set_ylabel("Clean completion (%)")
    axes[0].set_ylim(0, 105)
    axes[0].legend()
    hs = [max(c["attack_attempt_rate"], c["planner_attack_attempt_rate"])
          for c in data["cells"]]
    rs = [c["attack_realized_harm_rate"] for c in data["cells"]]
    axes[1].scatter(hs, rs, c=[METHOD_COLORS.assign(c["scaffold"]) for c in data["cells"]], s=55)
    for c, x, y in zip(data["cells"], hs, rs):
        if c["planner_attack_attempt_rate"] > c["attack_realized_harm_rate"]:
            axes[1].annotate(f"{c['model'].capitalize()}\nvalidator", (x, y),
                             xytext=(6, 7) if y == 0 else (-8, -5), textcoords="offset points",
                             ha="left" if y == 0 else "right", va="bottom" if y == 0 else "top", fontsize=13)
    axes[1].plot([0, max(hs + [1])], [0, max(hs + [1])], color="#8a8a8a", linestyle="--")
    axes[1].set_xlabel("Attempted harm (%)")
    axes[1].set_ylabel("Realized harm (%)")
    finish(fig, "utility_and_enforcement", "Left: clean utility versus model-call cost. Right: attempted versus realized harm; points below the diagonal indicate scaffold interception.", "Safety gains are audited against utility and separated into decision and enforcement effects.", meta)


def defects(data: dict, meta: list) -> None:
    rows = data["by_authorization_defect"]
    levels = sorted({r["mechanism"] for r in rows})
    values = []
    for level in levels:
        selected = [r["attack_harm_rate"] for r in rows if r["mechanism"] == level]
        values.append(float(np.mean(selected)))
    fig, ax = plt.subplots(figsize=(7.3, 3.5))
    ax.bar(np.arange(len(levels)), values, color="#0072B2")
    for x, value in enumerate(values): ax.text(x, value + .4, f"{value:.1f}", ha="center", va="bottom", fontsize=12)
    ax.set_xticks(np.arange(len(levels)), [x.replace("_", "\n") for x in levels])
    ax.set_ylabel("Mean realized harm across cells (%)")
    ax.set_ylim(0, max(20, max(values) + 5))
    finish(fig, "defect_diagnostic", "Descriptive harm rates by authorization-record defect, averaged across the twelve model-scaffold cells.", "Every realized violation is concentrated in the unverified-channel defect; identity, scope, and expiry defects produce none.", meta)


def matrix(meta: list) -> None:
    data = load("comparison_matrix.json")
    rows = [row["name"] for row in data["rows"]]
    keys = data["columns"][1:]
    cols = ["Security\noutcome", "Same cases\nacross stacks", "Clean\nutility",
            "Rank\nportability", "Executable /\nfixed oracle"]
    cells = [["?" if row[key] == "no" else row[key] for key in keys] for row in data["rows"]]
    quant = [row["cases"] for row in data["rows"]]
    fig, ax = plt.subplots(figsize=(10.8, 4.2))
    comparison_matrix(ax, rows, cols, cells, ours_row=0, quant_col=quant, quant_label="Cases")
    finish(fig, "comparison_matrix", "Abstract-verified capability comparison with nearby agent-system benchmarks; a question mark means not established by the retained abstract.", "ScaffoldRankBench makes cross-scaffold security-ranking portability the controlled estimand.", meta)


def main() -> None:
    style()
    data = load("aggregate.json")
    meta = []
    teaser(data, meta)
    plt.rcParams.update({"font.size": 13, "axes.labelsize": 13, "xtick.labelsize": 12, "ytick.labelsize": 12, "legend.fontsize": 12})
    factorial(data, meta)
    utility_cost(data, meta)
    defects(data, meta)
    matrix(meta)
    (FIGURES / "figures.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(f"wrote {len(meta)} figures")


if __name__ == "__main__":
    main()
