"""Show all decisions, retaining clarification and invalid responses as separate outcomes."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from paper_style import style


ROOT = Path(__file__).resolve().parents[1]


def draw(study, views, view_names, labels, filename):
    data = json.loads((ROOT / "results" / (study + ".json")).read_text())
    assert data["complete"]
    models = ["gpt-5.6-luna", "gpt-5.6-sol"]
    colors = ["#27789a", "#cf7e34", "#a9afb7", "#9d4562"]
    style()
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 13,
                         "xtick.labelsize": 12, "ytick.labelsize": 12,
                         "pdf.fonttype": 42, "axes.spines.top": False,
                         "axes.spines.right": False})
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 4.7), sharey=True)
    positions = np.arange(6)
    for ax, model in zip(axes, models):
        rows = [next(row for row in data["groups"]
                     if row["model"] == model and row["view"] == view
                     and row["unsafe"] == unsafe and row["mechanism"] == "ALL")
                for view in views for unsafe in [False, True]]
        left = np.zeros(6)
        for decision, color in zip(labels, colors):
            counts = np.array([row["decisions"].get(decision, 0) for row in rows])
            values = np.array([100 * count / row["n"] for count, row in zip(counts, rows)])
            ax.barh(positions, values, left=left, height=.64, color=color,
                    edgecolor="white", linewidth=.4, label=decision)
            for y, width, start, count in zip(positions, values, left, counts):
                if width >= 13:
                    ax.text(start + width / 2, y, str(count), ha="center", va="center",
                            color="white" if color in [colors[0], colors[3]] else "black", fontsize=12)
            left += values
        ax.set_title("Luna" if model.endswith("luna") else "Sol", fontsize=14)
        ax.set_xlim(0, 100)
        ax.set_xticks([0, 25, 50, 75, 100])
        ax.set_xlabel("Recorded decisions (%)")
        ax.set_axisbelow(True)
        ax.grid(axis="x", alpha=.15)
        for y in [1.5, 3.5]:
            ax.axhline(y, color="#d8d8d8", linewidth=.6)
    axes[0].set_yticks(positions, [name + (": unsafe" if unsafe else ": safe")
                                 for name in view_names for unsafe in [False, True]])
    axes[0].invert_yaxis()
    handles, names = axes[0].get_legend_handles_labels()
    fig.legend(handles, names, loc="lower center", ncol=4, frameon=False, fontsize=12)
    fig.subplots_adjust(left=.24, right=.985, bottom=.23, top=.90, wspace=.10)
    for target in [ROOT / "figures", ROOT.parents[1] / "paper/figures"]:
        target.mkdir(exist_ok=True)
        fig.savefig(target / (filename + ".pdf"), bbox_inches="tight")
        fig.savefig(target / (filename + ".png"), dpi=180, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    draw("binding_repair_v1", ["history", "state", "bound_state"],
         ["History", "State", "Bound state"], ["ALLOW", "BLOCK", "ASK", "INVALID"],
         "binding_repair_decisions")
    draw("atbench_observation_v1", ["full", "action_log", "last_action"],
         ["Full record", "Action log", "Last action"], ["SAFE", "UNSAFE", "INSUFFICIENT", "INVALID"],
         "atbench_observation_decisions")
