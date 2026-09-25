"""Shared publication style vendored from the pipeline template."""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

_PALETTE = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9", "#F0E442", "#999999"]
GRAY = "#8a8a8a"


class _MethodColors:
    def __init__(self):
        self._map: dict[str, str] = {}

    def assign(self, method: str) -> str:
        if method not in self._map:
            self._map[method] = _PALETTE[len(self._map) % len(_PALETTE)]
        return self._map[method]


METHOD_COLORS = _MethodColors()


def style() -> None:
    plt.rcParams.update({
        "font.size": 11, "axes.labelsize": 12, "axes.titlesize": 12,
        "legend.fontsize": 10, "xtick.labelsize": 10, "ytick.labelsize": 10,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.linewidth": .8, "axes.grid": True, "grid.alpha": .25,
        "grid.linewidth": .5, "legend.frameon": False,
        "figure.dpi": 120, "savefig.bbox": "tight", "savefig.dpi": 300,
        "pdf.fonttype": 42,
    })


def annotate_headline(ax, x, y, text: str, color: str = "#D55E00") -> None:
    ax.annotate(text, (x, y), textcoords="offset points", xytext=(0, 10),
                ha="center", fontweight="bold", color=color, fontsize=12)


def bar_with_error(ax, labels, means, errs, colors, value_fmt: str = "{:.1f}"):
    xs = np.arange(len(labels))
    bars = ax.bar(xs, means, yerr=errs, color=colors, capsize=3, error_kw={"linewidth": .9})
    for x, mean, err in zip(xs, means, errs):
        ax.annotate(value_fmt.format(mean), (x, mean + (err or 0)), ha="center", xytext=(0, 3), textcoords="offset points", fontsize=10)
    ax.set_xticks(xs, labels)
    return bars


def save(fig, path_stem: str) -> None:
    fig.savefig(f"{path_stem}.pdf")
    fig.savefig(f"{path_stem}.png", dpi=300)
    plt.close(fig)
