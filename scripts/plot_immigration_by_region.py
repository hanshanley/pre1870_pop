#!/usr/bin/env python3
"""
plot_immigration_by_region.py

Plot legal immigration to the United States by world region of last residence,
by decade, from 1820 to 2016.

Purpose
-------
Visualize the well-known "waves" of U.S. immigration: the 19th-century dominance
of Northern & Western Europe, the 1890-1920 surge from Southern & Eastern Europe,
and the post-1965 shift toward Latin America, Asia, and Africa.

Data
----
Reads data/immigration_by_region_decade.csv, produced by
scripts/build_immigration_by_region.py from a verbatim transcription of
DHS/OHSS Yearbook of Immigration Statistics 2016, Table 2 (pp. 6-11). Region
totals reproduce the source's published continental and grand totals exactly.

Styling follows the project's Substack-style theme (see notebooks/old_stock_analysis.ipynb).

Outputs (outputs/)
------------------
1. immigration_by_region_absolute.png        - stacked area, admissions per decade.
2. immigration_by_region_share.png           - 100%-normalized composition per decade.
3. immigration_by_region_small_multiples.png - one panel per region.
"""

import argparse
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator

# --- Substack-style theme (matches the notebook) ---
BG = "#F7F5F0"
TEXT = "#1A1A1A"
MUTED = "#6B6B6B"
GRID = "#D6D3CC"

plt.rcParams.update(
    {
        "figure.facecolor": BG,
        "axes.facecolor": BG,
        "savefig.facecolor": BG,
        "text.color": TEXT,
        "axes.labelcolor": TEXT,
        "axes.edgecolor": MUTED,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "font.size": 11,
    }
)

# Region draw order (bottom -> top) grouped by continental family, with a
# muted/earthy palette consistent with the project theme.
REGION_ORDER = [
    "Northern & Western Europe",
    "Southern Europe",
    "Eastern Europe",
    "East Asia",
    "South Asia",
    "Southeast Asia",
    "Other Asia",
    "Middle East & North Africa",
    "Sub-Saharan Africa",
    "Mexico & Central America",
    "Caribbean",
    "South America",
    "Canada",
    "Other & not specified",
]

REGION_COLORS = {
    "Northern & Western Europe": "#2C5E7E",
    "Southern Europe": "#5B8BA6",
    "Eastern Europe": "#9DC0D4",
    "East Asia": "#7B2D26",
    "South Asia": "#C85A3D",
    "Southeast Asia": "#DD8A5E",
    "Other Asia": "#E9C39B",
    "Middle East & North Africa": "#C2993E",
    "Sub-Saharan Africa": "#4A7C59",
    "Mexico & Central America": "#6E9151",
    "Caribbean": "#9DBE7E",
    "South America": "#C7D6A8",
    "Canada": "#8C7B6B",
    "Other & not specified": "#B5AFA6",
}

# Self-documenting legend labels (the source only itemizes certain countries).
DISPLAY = {
    "East Asia": "East Asia (China, Japan, Korea, Taiwan, HK)",
    "South Asia": "South Asia (India)",
    "Southeast Asia": "Southeast Asia (Philippines, Vietnam)",
    "Other Asia": "Other Asia (Pakistan, Iraq, Indonesia, ...)",
    "Middle East & North Africa": "Middle East & N. Africa",
}

SOURCE_NOTE = (
    "Source: DHS/OHSS Yearbook of Immigration Statistics 2016, Table 2 "
    "(persons obtaining LPR status by region of last residence)."
)


def load(path):
    df = pd.read_csv(path)
    pivot = (
        df.pivot_table(
            index=["decade_start", "decade_label"],
            columns="region",
            values="immigrants",
            aggfunc="sum",
        )
        .reset_index()
        .sort_values("decade_start")
    )
    regions = [r for r in REGION_ORDER if r in pivot.columns]
    return pivot, regions


def _legend_labels(regions):
    return [DISPLAY.get(r, r) for r in regions]


def _smooth(x, series, n=500):
    """Shape-preserving (PCHIP) interpolation onto a dense grid.

    PCHIP is monotone and non-overshooting, so smoothed bands never dip below
    zero or invent peaks the decade data doesn't support.
    """
    xs = np.linspace(x[0], x[-1], n)
    out = [np.clip(PchipInterpolator(x, y)(xs), 0, None) for y in series]
    return xs, out


def _xaxis(ax, pivot):
    x = np.arange(len(pivot))
    ax.set_xticks(x)
    ax.set_xticklabels(pivot["decade_label"], rotation=45, ha="right", fontsize=9)
    if pivot["decade_start"].iloc[-1] == 2010:
        ax.get_xticklabels()[-1].set_color("#9A4A36")
    return x


def stacked_area_absolute(pivot, regions, out_path):
    fig, ax = plt.subplots(figsize=(12.5, 7))
    x = _xaxis(ax, pivot)
    ys = [pivot[r].values / 1e6 for r in regions]
    colors = [REGION_COLORS[r] for r in regions]
    xs, ys_s = _smooth(x, ys)
    ax.stackplot(xs, ys_s, colors=colors, edgecolor=BG, linewidth=0.5)

    ax.set_ylabel("Immigrants admitted per decade")
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"{v:.0f}M"))
    ax.set_title(
        "Legal immigration to the United States by region of origin, 1820\u20132016",
        fontweight="bold",
        pad=14,
        fontsize=14,
    )
    ax.margins(x=0)
    ax.grid(axis="y", linestyle="-", linewidth=0.5, color=GRID)
    ax.set_axisbelow(True)

    handles = [plt.Rectangle((0, 0), 1, 1, color=REGION_COLORS[r]) for r in regions]
    ax.legend(
        handles[::-1],
        _legend_labels(regions)[::-1],
        loc="upper left",
        frameon=False,
        fontsize=8.5,
        labelcolor=TEXT,
    )
    fig.text(
        0.01, 0.005,
        SOURCE_NOTE + "  2010\u201316 is a partial decade (7 fiscal years).",
        ha="left", fontsize=8, color=MUTED, style="italic",
    )
    plt.tight_layout()
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out_path}")


def stacked_area_share(pivot, regions, out_path):
    fig, ax = plt.subplots(figsize=(12.5, 7))
    x = _xaxis(ax, pivot)
    abs_series = [pivot[r].values.astype(float) for r in regions]
    colors = [REGION_COLORS[r] for r in regions]
    xs, abs_s = _smooth(x, abs_series)
    totals = np.sum(abs_s, axis=0)
    ys = [100.0 * s / totals for s in abs_s]
    ax.stackplot(xs, ys, colors=colors, edgecolor=BG, linewidth=0.5)

    ax.set_ylabel("Share of decade's immigrants (%)")
    ax.set_ylim(0, 100)
    ax.set_title(
        "Composition of U.S. immigration by region of origin, 1820\u20132016",
        fontweight="bold",
        pad=14,
        fontsize=14,
    )
    ax.margins(x=0)

    handles = [plt.Rectangle((0, 0), 1, 1, color=REGION_COLORS[r]) for r in regions]
    ax.legend(
        handles[::-1],
        _legend_labels(regions)[::-1],
        loc="center left",
        bbox_to_anchor=(1.0, 0.5),
        frameon=False,
        fontsize=8.5,
        labelcolor=TEXT,
    )
    fig.text(
        0.01, 0.005, SOURCE_NOTE, ha="left", fontsize=8, color=MUTED, style="italic"
    )
    plt.tight_layout()
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out_path}")


def small_multiples(pivot, regions, out_path):
    x = np.arange(len(pivot))
    ncol = 3
    nrow = int(np.ceil(len(regions) / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(13, 2.3 * nrow), sharex=True)
    axes = axes.ravel()
    for i, r in enumerate(regions):
        ax = axes[i]
        ax.fill_between(x, pivot[r].values / 1e6, color=REGION_COLORS[r], alpha=0.9)
        ax.set_title(DISPLAY.get(r, r), fontsize=9.5, color=TEXT)
        ax.grid(axis="y", linewidth=0.4, color=GRID)
        ax.set_axisbelow(True)
        ax.margins(x=0)
        ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda v, _: f"{v:.1f}M"))
    for j in range(len(regions), len(axes)):
        axes[j].axis("off")
    for ax in axes[-ncol:]:
        ax.set_xticks(x[::2])
        ax.set_xticklabels(pivot["decade_label"].values[::2], rotation=45, ha="right", fontsize=8)
    fig.suptitle(
        "U.S. immigration by region of origin (millions per decade), 1820\u20132016",
        fontweight="bold",
        fontsize=14,
    )
    fig.text(0.01, 0.005, SOURCE_NOTE, ha="left", fontsize=8, color=MUTED, style="italic")
    fig.tight_layout(rect=[0, 0.02, 1, 0.97])
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out_path}")


def main():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--input", default=os.path.join(here, "data", "immigration_by_region_decade.csv")
    )
    ap.add_argument("--outputs-dir", default=os.path.join(here, "outputs"))
    args = ap.parse_args()

    os.makedirs(args.outputs_dir, exist_ok=True)
    pivot, regions = load(args.input)

    stacked_area_absolute(
        pivot, regions, os.path.join(args.outputs_dir, "immigration_by_region_absolute.png")
    )
    stacked_area_share(
        pivot, regions, os.path.join(args.outputs_dir, "immigration_by_region_share.png")
    )
    small_multiples(
        pivot, regions, os.path.join(args.outputs_dir, "immigration_by_region_small_multiples.png")
    )


if __name__ == "__main__":
    main()
