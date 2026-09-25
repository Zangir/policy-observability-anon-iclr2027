"""Build the paper figures from results/figure_data.json using paper_style.py.
Figures read ONLY from the results JSON. Emits PDF + 300-dpi PNG into paper/figures/.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import paper_style as ps
from paper_style import METHOD_COLORS as MC

REPO = Path(__file__).resolve().parents[1]  # decision_invariance/ repo root (portable)
DATA = json.loads((REPO / "results/figure_data.json").read_text())
OUT = REPO / "figures"
OUT.mkdir(parents=True, exist_ok=True)
ps.style()


def fig1_teaser():
    d = {"self_contained": 776, "absent": 2281, "total": 3057}
    fig, ax = plt.subplots(figsize=(7.2, 2.6))
    ax.barh([0], [d["self_contained"]], color="#009E73", label="scored condition present in agent-visible input")
    ax.barh([0], [d["absent"]], left=[d["self_contained"]], color="#D55E00",
            label="scored condition absent (unattributable)")
    ax.set_xlim(0, d["total"])
    ax.set_yticks([])
    ax.set_xlabel("ST-WebAgentBench scored conditions (n=3{,}057)")
    ps.annotate_headline(ax, d["self_contained"] + d["absent"] / 2, 0,
                         "74.6% absent")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.45), ncol=1, frameon=False, fontsize=9)
    ax.set_title("When is a policy violation a model failure?\n"
                 "Attribution needs R1 sufficiency, R2 observation contract, P1 invariance, A1 denominator",
                 fontsize=10, loc="left")
    fig.tight_layout()
    ps.save(fig, str(OUT / "fig1_teaser"))


def fig2_matrix():
    m = DATA["matrix"]
    fig, ax = plt.subplots(figsize=(7.6, 2.8))
    ps.comparison_matrix(ax, m["rows"], m["cols"], m["cells"],
                         quant_col=m["quant_col"], quant_label=m["quant_label"])
    fig.tight_layout()
    ps.save(fig, str(OUT / "fig2_matrix"))


def fig3_authentigrant():
    a = DATA["authentigrant"]
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    colors = [MC.assign("Haiku"), MC.assign("Haiku"), MC.assign("Sonnet"),
              MC.assign("Haiku-ledger"), MC.assign("gate")]
    errs = [(lo + hi) / 2 for lo, hi in zip(a["err_lo"], a["err_hi"])]
    ps.bar_with_error(ax, a["labels"], a["unsafe_pct"], errs, colors, value_fmt="{:.1f}%")
    ax.set_ylabel("Unsafe execution (%)")
    ax.set_title("AuthentiGrant: unsafe execution of unauthorized actions", fontsize=10, loc="left")
    fig.tight_layout()
    ps.save(fig, str(OUT / "fig3_authentigrant"))


def fig4_composition():
    c = DATA["composition"]
    xs = np.arange(len(c["labels"]))
    w = 0.38
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    ax.bar(xs - w / 2, c["harm_pct"], w, color="#D55E00", label="realized compositional harm")
    ax.bar(xs + w / 2, c["clean_pct"], w, color="#009E73", label="clean completion")
    for x, v in zip(xs - w / 2, c["harm_pct"]):
        ax.annotate(f"{v:.0f}%", (x, v), ha="center", xytext=(0, 3), textcoords="offset points", fontsize=9)
    ax.set_xticks(xs, c["labels"])
    ax.set_ylabel("Percent")
    ax.set_ylim(0, 100)
    ax.legend(frameon=False, fontsize=9)
    ax.set_title("CompositionalHarmBench: only a trajectory monitor removes composed harm", fontsize=10, loc="left")
    fig.tight_layout()
    ps.save(fig, str(OUT / "fig4_composition"))


def fig5_invariance():
    v = DATA["invariance"]
    xs = np.arange(len(v["contrasts"]))
    w = 0.38
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    ax.bar(xs - w / 2, v["cross"], w, color="#0072B2", label="cross-arm disagreement")
    ax.bar(xs + w / 2, v["within"], w, color="#999999", label="within-arm repeat noise")
    ax.set_xticks(xs, v["contrasts"])
    ax.set_ylabel("Disagreement rate")
    ax.set_ylim(0, max(v["cross"] + v["within"]) * 1.6 + 1e-6)
    for i, e in enumerate(v["excess"]):
        ax.annotate(f"excess = {e:.2f}", (i, max(v['cross'][i], v['within'][i])),
                    ha="center", xytext=(0, 6), textcoords="offset points", fontsize=9, color="#D55E00")
    ax.legend(frameon=False, fontsize=9)
    ax.set_title("Decision invariance: reserialization moves decisions no more than repeat noise (Haiku)",
                 fontsize=9.5, loc="left")
    fig.tight_layout()
    ps.save(fig, str(OUT / "fig5_invariance"))


if __name__ == "__main__":
    fig1_teaser(); fig2_matrix(); fig3_authentigrant(); fig4_composition(); fig5_invariance()
    print("figures written to", OUT)
