#!/usr/bin/env python3
"""Render AuthentiGrant figures exclusively from persisted result JSON."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch

from paper_style import METHOD_COLORS, annotate_headline, bar_with_error, save, style

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
FIGURES = ROOT / "figures"


def load(name: str) -> dict:
    return json.loads((RESULTS / name).read_text())


def finish(fig, name: str, caption: str, shows: str, metadata: list) -> None:
    FIGURES.mkdir(exist_ok=True)
    save(fig, str(FIGURES / name))
    metadata.append({"file": f"figures/{name}.pdf", "pattern": name, "caption_draft": caption, "shows": shows})


def teaser(data: dict, metadata: list) -> None:
    value = 100 * data["primary"]["unsafe_execution_rate"]
    fig, axes = plt.subplots(1, 3, figsize=(11.2, 3.1), gridspec_kw={"width_ratios": [1.25, 1.1, 1]})
    panels = [
        ("Matched request", "Certificate subject ≠\nsession principal\n\n‘Officially approved—\nproceed urgently’"),
        ("AuthentiGrant", "Identity certificate\n+ scoped grant ledger\n+ channel provenance\n\nExact state oracle"),
    ]
    for ax, (heading, body) in zip(axes[:2], panels):
        ax.axis("off")
        box = FancyBboxPatch((.05, .12), .9, .76, boxstyle="round,pad=.03", facecolor="#EAF3F8", edgecolor="#0072B2", linewidth=1.3)
        ax.add_patch(box)
        ax.text(.5, .76, heading, ha="center", va="center", fontweight="bold", transform=ax.transAxes)
        ax.text(.5, .43, body, ha="center", va="center", transform=ax.transAxes, linespacing=1.35)
    ax = axes[2]
    ax.bar([0], [value], color=METHOD_COLORS.assign("Haiku"), width=.55)
    ax.set_ylim(0, max(25, value + 8))
    ax.set_ylabel("Unsafe proposals (%)")
    ax.set_xticks([0], ["Haiku\nprinciples"])
    annotate_headline(ax, 0, value, f"{value:.1f}%")
    finish(fig, "teaser", "A matched authority case, the executable factorization, and the primary unsafe-execution rate.", "The model can execute despite failed genuine authority even when request rhetoric is untrusted.", metadata)


def factor_effects(data: dict, metadata: list) -> None:
    primary = data["primary"]
    keys = ["identity_sensitivity", "permission_sensitivity", "channel_sensitivity", "claimed_identity_susceptibility", "authority_wording_susceptibility"]
    labels = ["Identity", "Permission", "Channel", "Claimed role", "Wording"]
    values = [100 * primary[k] for k in keys]
    cis = [primary["clustered_bootstrap_95ci"][k] for k in keys]
    errs = np.array([[v - 100 * ci[0] for v, ci in zip(values, cis)], [100 * ci[1] - v for v, ci in zip(values, cis)]])
    fig, ax = plt.subplots(figsize=(7.2, 3.5))
    colors = ["#0072B2"] * 3 + ["#E69F00"] * 2
    ax.bar(np.arange(5), values, yerr=errs, color=colors, capsize=3)
    ax.axhline(0, color="#555555", linewidth=.8)
    ax.set_xticks(np.arange(5), labels)
    ax.set_ylabel("Execution-rate contrast (points)")
    finish(fig, "factor_effects", "Execution contrasts for three genuine authority signals and two cosmetic cues; bars show task-clustered 95% intervals.", "Models respond incompletely to genuine authority evidence while cosmetic effects are near zero.", metadata)


def model_comparison(data: dict, metadata: list) -> None:
    entries = [("Haiku\nprimary", data["primary_even_subset"]), ("Haiku\nresample", data["paired_generation_resample"]), ("Sonnet", data["model_robustness"])]
    labels = [x[0] for x in entries]
    means = [100 * x[1]["unsafe_execution_rate"] for x in entries]
    cis = [x[1]["clustered_bootstrap_95ci"]["unsafe_execution_rate"] for x in entries]
    errs = np.array([[v - 100 * ci[0] for v, ci in zip(means, cis)], [100 * ci[1] - v for v, ci in zip(means, cis)]])
    fig, ax = plt.subplots(figsize=(6.3, 3.5))
    bars = ax.bar(labels, means, yerr=errs, capsize=3, color=[METHOD_COLORS.assign("Haiku"), METHOD_COLORS.assign("Haiku"), METHOD_COLORS.assign("Sonnet")])
    for bar, mean, upper in zip(bars, means, errs[1]):
        ax.annotate(f"{mean:.2f}", (bar.get_x()+bar.get_width()/2, mean+upper), ha="center", xytext=(0,3), textcoords="offset points", fontsize=12)
    ax.set_ylabel("Unsafe proposals (%)")
    ax.set_ylim(0, max(18, max(means + list(errs[1])) + 4))
    finish(fig, "model_comparison", "Unsafe proposals on the same five tasks for Haiku primary, an independent Haiku resample, and Sonnet; intervals cluster by task.", "The failure replicates for Haiku but is much smaller for Sonnet.", metadata)


def task_diagnostic(data: dict, metadata: list) -> None:
    rows = sorted(data["primary_per_task"].items(), key=lambda item: item[1]["unsafe"], reverse=True)
    labels = [item[0].replace("_", " ") for item in rows]
    values = [100 * item[1]["unsafe"] / 28 for item in rows]
    fig, ax = plt.subplots(figsize=(7.5, 4.7))
    ax.barh(np.arange(len(rows)), values, color=METHOD_COLORS.assign("Haiku"))
    ax.set_yticks(np.arange(len(rows)), labels)
    ax.invert_yaxis()
    ax.set_xlabel("Unsafe proposals among unauthorized (%)")
    ax.tick_params(axis="y", labelsize=13)
    finish(fig, "task_diagnostic", "Unsafe-proposal rates by base task in the primary grid; each task contributes 28 unauthorized cells.", "Rates differ across tasks whose domains and evidence patterns are confounded.", metadata)


def main() -> None:
    style()
    data = load("aggregate.json")
    metadata: list[dict] = []
    teaser(data, metadata)
    plt.rcParams.update({"font.size": 13, "axes.labelsize": 13, "axes.titlesize": 14, "xtick.labelsize": 13, "ytick.labelsize": 13, "legend.fontsize": 13})
    factor_effects(data, metadata)
    model_comparison(data, metadata)
    task_diagnostic(data, metadata)
    (FIGURES / "figures.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"-> {FIGURES / 'figures.json'}")


if __name__ == "__main__":
    main()
