"""Show complete observed coverage, source-specific rates and declared utility tradeoffs."""
from collections import Counter
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from paper_style import style

ROOT = Path(__file__).resolve().parents[1]


def save(fig, name):
    for directory in [ROOT / "figures", ROOT.parents[1] / "paper/figures"]:
        directory.mkdir(exist_ok=True)
        fig.savefig(directory / (name + ".pdf"), bbox_inches="tight")
        fig.savefig(directory / (name + ".png"), bbox_inches="tight", dpi=180)
    plt.close(fig)


def source_rates(data):
    sources = {"ActBench\n(reanalyzed)": data["actbench_shared_nominal_configs"],
               "AgentS4D\n(reported)": data["agents4d"], "HarnessRisk\n(reported)": data["harnessrisk"]}
    counts = Counter((row["harness"], row["model"]) for rows in sources.values() for row in rows)
    configs = sorted(key for key, count in counts.items() if count >= 2)
    array = np.full((len(configs), len(sources)), np.nan)
    for j, rows in enumerate(sources.values()):
        lookup = {(row["harness"], row["model"]): row["asr"] for row in rows}
        for i, key in enumerate(configs):
            if key in lookup:
                array[i, j] = 100 * lookup[key]
    fig, ax = plt.subplots(figsize=(8.7, 5.6))
    cmap = plt.colormaps["YlOrBr"].copy(); cmap.set_bad("#eaecef")
    im = ax.imshow(array, vmin=0, vmax=100, cmap=cmap, aspect="auto")
    for (i, j), value in np.ndenumerate(array):
        ax.text(j, i, f"{value:.1f}" if np.isfinite(value) else "unreported", ha="center", va="center",
                fontsize=13, color="white" if value > 75 else "black")
    ax.set_yticks(range(len(configs)), [h + " / " + m for h, m in configs], fontsize=12)
    ax.set_xticks(range(len(sources)), list(sources), fontsize=13)
    ax.tick_params(length=0); ax.grid(False)
    colorbar = fig.colorbar(im, ax=ax, fraction=.045, pad=.03)
    colorbar.set_label("Attack success (%)", fontsize=13)
    fig.subplots_adjust(left=.43, right=.91, bottom=.14, top=.99)
    save(fig, "external_source_rankings")


def coverage(data):
    rows = [row for row in data["profile_rows"] if row["context"] == "ALL"]
    models = sorted({row["model"] for row in rows})
    harnesses = sorted({row["backend"] for row in rows})
    array = np.zeros((len(models), len(harnesses)))
    for row in rows:
        array[models.index(row["model"]), harnesses.index(row["backend"])] = 1
    fig, ax = plt.subplots(figsize=(9.4, 6.5))
    ax.imshow(array, cmap=matplotlib.colors.ListedColormap(["#eceef0", "#27789a"]), aspect="auto")
    for (i, j), value in np.ndenumerate(array):
        if value:
            ax.text(j, i, "1,200", ha="center", va="center", color="white", fontsize=13)
    ax.set_yticks(range(len(models)), [model.split("/", 1)[-1] for model in models], fontsize=14)
    ax.set_xticks(range(len(harnesses)), harnesses, rotation=25, ha="right", fontsize=14)
    ax.set_title("ActBench: 20 observed cells; 70 unobserved", fontsize=14)
    ax.grid(False); ax.tick_params(length=0)
    fig.subplots_adjust(left=.29, right=.99, bottom=.16, top=.94)
    save(fig, "external_factorial_coverage")


def tradeoffs(data):
    rows = [row for row in data["profile_rows"] if row["context"] == "ALL"
            and row["model"] == "deepseek/deepseek-v4-pro"]
    rows.sort(key=lambda row: row["asr"])
    fig, ax = plt.subplots(figsize=(8.5, 4.7))
    y = np.arange(len(rows)); width = .23
    for offset, metric, name, color in [(-width, "safety", "Attack non-success", "#27789a"),
                                      (0, "task_pass", "Clean task completion", "#d29b3c"),
                                      (width, "balanced", "Equal-weight mean", "#6c7c8d")]:
        vals = [100 * row[metric] for row in rows]
        ax.barh(y + offset, vals, height=width, color=color, label=name)
        for position, value in zip(y + offset, vals):
            ax.text(value + 1, position, f"{value:.1f}", va="center", fontsize=11)
    ax.set_yticks(y, [row["backend"] for row in rows], fontsize=13)
    ax.invert_yaxis(); ax.set_xlim(0, 103); ax.set_xlabel("Recorded rate (%)", fontsize=13)
    handles, names = ax.get_legend_handles_labels()
    fig.legend(handles, names, loc="lower center", ncol=3, fontsize=11, frameon=False)
    fig.subplots_adjust(left=.17, right=.98, bottom=.19, top=.98)
    save(fig, "external_security_utility")


if __name__ == "__main__":
    style(); plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 13,
                                  "xtick.labelsize": 12, "ytick.labelsize": 12})
    report = json.loads((ROOT / "results/actbench_rank_audit.json").read_text())
    source_rates(json.loads((ROOT / "results/reported_panel_audit.json").read_text()))
    coverage(report)
    tradeoffs(report)
