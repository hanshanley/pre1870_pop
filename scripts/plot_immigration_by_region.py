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

Expected input
--------------
A tidy CSV (default: data/immigration_by_region_decade.csv) with columns:

    decade_start, decade_label, region, immigrants

The file is derived from DHS/OHSS Yearbook of Immigration Statistics 2016,
Table 2 (Persons Obtaining Lawful Permanent Resident Status by Region and
Selected Country of Last Residence). Per-decade region totals reproduce the
published continental and grand totals exactly.

Outputs
-------
1. A stacked-area chart of absolute admissions per decade.
2. A 100%-normalized stacked-area chart of each region's share per decade.
3. A small-multiples line chart, one panel per region.
"""

import argparse
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Region display order (continental grouping) and colors.
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
    "Canada, Oceania & Other",
]

REGION_COLORS = {
    "Northern & Western Europe": "#1f4e79",
    "Southern Europe": "#2e75b6",
    "Eastern Europe": "#9dc3e6",
    "East Asia": "#7f3f00",
    "South Asia": "#c55a11",
    "Southeast Asia": "#ed7d31",
    "Other Asia": "#f4b183",
    "Middle East & North Africa": "#7030a0",
    "Sub-Saharan Africa": "#375623",
    "Mexico & Central America": "#548235",
    "Caribbean": "#a9d18e",
    "South America": "#c5e0b4",
    "Canada, Oceania & Other": "#a6a6a6",
}


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


def stacked_area_absolute(pivot, regions, out_path):
    x = np.arange(len(pivot))
    ys = [pivot[r].values / 1e6 for r in regions]
    colors = [REGION_COLORS[r] for r in regions]

    fig, ax = plt.subplots(figsize=(13, 7))
    ax.stackplot(x, ys, labels=regions, colors=colors, edgecolor="white", linewidth=0.3)
    ax.set_xticks(x)
    ax.set_xticklabels(pivot["decade_label"], rotation=45, ha="right")
    ax.set_ylabel("Immigrants admitted (millions)")
    ax.set_title(
        "Legal immigration to the United States by region of last residence, 1820\u20132016",
        fontsize=14,
        fontweight="bold",
    )
    ax.margins(x=0)
    ax.grid(axis="y", alpha=0.3)
    handles, lbls = ax.get_legend_handles_labels()
    ax.legend(
        handles[::-1],
        lbls[::-1],
        loc="upper left",
        fontsize=9,
        frameon=False,
        ncol=1,
    )
    fig.text(
        0.5,
        -0.02,
        "Source: DHS/OHSS Yearbook of Immigration Statistics 2016, Table 2. "
        "2010\u201316 is a partial decade (7 fiscal years).",
        ha="center",
        fontsize=8,
        color="#555555",
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out_path}")


def stacked_area_share(pivot, regions, out_path):
    x = np.arange(len(pivot))
    totals = pivot[regions].sum(axis=1).values
    ys = [100.0 * pivot[r].values / totals for r in regions]
    colors = [REGION_COLORS[r] for r in regions]

    fig, ax = plt.subplots(figsize=(13, 7))
    ax.stackplot(x, ys, labels=regions, colors=colors, edgecolor="white", linewidth=0.3)
    ax.set_xticks(x)
    ax.set_xticklabels(pivot["decade_label"], rotation=45, ha="right")
    ax.set_ylabel("Share of decade's immigrants (%)")
    ax.set_ylim(0, 100)
    ax.set_title(
        "Composition of U.S. immigration by region of last residence, 1820\u20132016",
        fontsize=14,
        fontweight="bold",
    )
    ax.margins(x=0)
    handles, lbls = ax.get_legend_handles_labels()
    ax.legend(
        handles[::-1],
        lbls[::-1],
        loc="center left",
        bbox_to_anchor=(1.0, 0.5),
        fontsize=9,
        frameon=False,
    )
    fig.text(
        0.5,
        -0.02,
        "Source: DHS/OHSS Yearbook of Immigration Statistics 2016, Table 2.",
        ha="center",
        fontsize=8,
        color="#555555",
    )
    fig.tight_layout()
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out_path}")


def small_multiples(pivot, regions, out_path):
    x = np.arange(len(pivot))
    ncol = 3
    nrow = int(np.ceil(len(regions) / ncol))
    fig, axes = plt.subplots(nrow, ncol, figsize=(14, 2.4 * nrow), sharex=True)
    axes = axes.ravel()
    for i, r in enumerate(regions):
        ax = axes[i]
        ax.fill_between(x, pivot[r].values / 1e6, color=REGION_COLORS[r], alpha=0.85)
        ax.set_title(r, fontsize=10)
        ax.grid(alpha=0.25)
        ax.margins(x=0)
    for j in range(len(regions), len(axes)):
        axes[j].axis("off")
    for ax in axes[-ncol:]:
        ax.set_xticks(x[::2])
        ax.set_xticklabels(pivot["decade_label"].values[::2], rotation=45, ha="right", fontsize=8)
    fig.suptitle(
        "U.S. immigration by region of last residence (millions per decade), 1820\u20132016",
        fontsize=14,
        fontweight="bold",
    )
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(out_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out_path}")


def main():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--input",
        default=os.path.join(here, "data", "immigration_by_region_decade.csv"),
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
