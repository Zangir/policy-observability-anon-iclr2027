"""paper_style — one import gives every figure the anchor-paper look.

Vendor this file into the experiment repo (scripts/paper_style.py) and use it in
make_figures.py. It encodes the visual language of the anchor papers (PIPELINE.md §0c):
consistent palette, one hue per method, clean spines, annotated headline numbers,
shaded uncertainty bands, and a comparison-matrix renderer.

Usage:
    from paper_style import style, METHOD_COLORS, annotate_headline, band, comparison_matrix
    style()                             # once, before any figure
    c = METHOD_COLORS.assign("ours")    # stable color per method across ALL figures
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# Okabe–Ito colorblind-safe palette; "ours" is always the first (blue)
_PALETTE = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7",
            "#56B4E9", "#F0E442", "#999999"]
GRAY = "#8a8a8a"


class _MethodColors:
    """Stable method→color mapping reused across every figure in the paper."""
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
        "axes.linewidth": 0.8, "axes.grid": True, "grid.alpha": 0.25,
        "grid.linewidth": 0.5, "legend.frameon": False,
        "figure.dpi": 120, "savefig.bbox": "tight", "savefig.dpi": 300,
        "pdf.fonttype": 42,  # editable text in the PDF (camera-ready requirement)
    })


def annotate_headline(ax, x, y, text: str, color: str = "#D55E00") -> None:
    """Bold callout for THE number (anchor papers always label the headline point)."""
    ax.annotate(text, (x, y), textcoords="offset points", xytext=(0, 10),
                ha="center", fontweight="bold", color=color, fontsize=12)


def band(ax, x, lo, hi, color: str, label: str | None = None):
    """Shaded uncertainty band (the [5th,95th] random-null band, CI ribbon, ...)."""
    return ax.fill_between(x, lo, hi, color=color, alpha=0.18, linewidth=0, label=label)


def bar_with_error(ax, labels, means, errs, colors, value_fmt: str = "{:.2f}"):
    """Anchor-style bar chart: error bars + the value printed above each bar."""
    xs = np.arange(len(labels))
    bars = ax.bar(xs, means, yerr=errs, color=colors, capsize=3,
                  error_kw={"linewidth": 0.9})
    for x, m, e in zip(xs, means, errs):
        ax.annotate(value_fmt.format(m), (x, m + (e or 0)), ha="center",
                    xytext=(0, 3), textcoords="offset points", fontsize=10)
    ax.set_xticks(xs, labels)
    return bars


def comparison_matrix(ax, rows, cols, cells, ours_row: int | None = None,
                      quant_col: list | None = None, quant_label: str = ""):
    """F-D comparison matrix: incumbents × capabilities with ✓/✗/±, ours highlighted,
    plus an optional quantitative bar column. cells[i][j] ∈ {'yes','no','partial',str}."""
    n_r, n_c = len(rows), len(cols)
    ax.set_xlim(-0.5, n_c + (1.5 if quant_col else -0.5) + 0.5)
    ax.set_ylim(-0.5, n_r - 0.5)
    ax.invert_yaxis()
    ax.axis("off")
    mark = {"yes": ("✓", "#009E73"), "no": ("✗", "#D55E00"),
            "partial": ("±", "#E69F00")}
    for j, c in enumerate(cols):
        ax.text(j, -0.9, c, ha="center", fontweight="bold", fontsize=10, wrap=True)
    if quant_col:
        ax.text(n_c + 0.75, -0.9, quant_label, ha="center", fontweight="bold", fontsize=10)
        qmax = max(q for q in quant_col if isinstance(q, (int, float))) or 1
    for i, r in enumerate(rows):
        bold = (i == ours_row)
        if bold:
            ax.axhspan(i - 0.45, i + 0.45, color="#0072B2", alpha=0.08)
        ax.text(-0.7, i, r, ha="right", va="center", fontsize=10,
                fontweight="bold" if bold else "normal")
        for j in range(n_c):
            v = cells[i][j]
            sym, col = mark.get(v, (str(v), "#333333"))
            ax.text(j, i, sym, ha="center", va="center", color=col,
                    fontsize=13 if v in mark else 9,
                    fontweight="bold" if v in mark else "normal")
        if quant_col:
            q = quant_col[i]
            if isinstance(q, (int, float)):
                w = 1.2 * q / qmax
                ax.barh(i, w, left=n_c + 0.15, height=0.5,
                        color="#0072B2" if bold else "#bfbfbf")
                ax.text(n_c + 0.2 + w, i, f"{q:,.0f}", va="center", fontsize=9)
            else:
                ax.text(n_c + 0.75, i, str(q), va="center", ha="center",
                        fontsize=9, color=GRAY)


def save(fig, path_stem: str) -> None:
    """PDF + 300-dpi PNG, the pair every figure ships as."""
    fig.savefig(f"{path_stem}.pdf")
    fig.savefig(f"{path_stem}.png", dpi=300)
    plt.close(fig)
