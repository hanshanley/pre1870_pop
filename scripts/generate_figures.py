#!/usr/bin/env python3
"""
generate_figures.py

Regenerate the four headline PNG figures without requiring a Census API key or
Jupyter. The figures are reproduced exactly as in notebooks/old_stock_analysis.ipynb
but the state/EC inputs are read from the committed agent-model outputs so the
images stay in sync with the corrected White-only estimates.

Figures produced (written to outputs/):
  - pct_white_heritage_over_time.png      (national time series, national model)
  - raw_headcount_white_heritage.png      (national headcount)
  - map_white_heritage_pct_by_state.png   (state tile cartogram, agent estimates)
  - map_hypothetical_ec_2024_tile_mosaic.png(EC tile cartogram, agent estimates)

Usage:
    python scripts/generate_figures.py
"""

from __future__ import annotations

import os
import pathlib
import sys

import matplotlib
matplotlib.use("Agg")  # headless: no display required

import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import matplotlib.patheffects as pe
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from matplotlib.patches import FancyBboxPatch, Circle, Rectangle
from matplotlib.collections import PatchCollection

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
OUT = ROOT / "outputs"

from pre1870_ancestry_model import ModelParams, DECADE_DATA, simulate
from hypothetical_ec_reapportionment import apportion_house_huntington_hill, EV_2024

# ── Substack-style theme (matches the notebook) ────────────────────────────
SUBSTACK_BG = "#F7F5F0"
SUBSTACK_CARD = "#EFEDE8"
SUBSTACK_TEXT = "#1A1A1A"
SUBSTACK_MUTED = "#6B6B6B"
SUBSTACK_ACCENT = "#C85A3D"
SUBSTACK_BLUE = "#3D6F8C"
SUBSTACK_GOLD = "#C2993E"
SUBSTACK_GREEN = "#4A7C59"
SUBSTACK_GRID = "#D6D3CC"

plt.rcParams.update({
    "figure.facecolor": SUBSTACK_BG,
    "axes.facecolor": SUBSTACK_BG,
    "savefig.facecolor": SUBSTACK_BG,
    "text.color": SUBSTACK_TEXT,
    "axes.labelcolor": SUBSTACK_TEXT,
    "xtick.color": SUBSTACK_MUTED,
    "ytick.color": SUBSTACK_MUTED,
    "axes.edgecolor": SUBSTACK_GRID,
    "grid.color": SUBSTACK_GRID,
    "grid.alpha": 0.6,
    "grid.linewidth": 0.5,
    "font.family": "serif",
    "font.size": 12,
    "axes.titlesize": 16,
    "axes.labelsize": 13,
    "figure.titlesize": 18,
    "legend.framealpha": 0.0,
    "legend.fontsize": 11,
    "axes.spines.top": False,
    "axes.spines.right": False,
})

# Shared tile layout for both state cartograms.
TILE = {
    'AK': (0, 0), 'ME': (10, 0),
    'WI': (5, 1), 'VT': (9, 1), 'NH': (10, 1),
    'WA': (0, 2), 'ID': (1, 2), 'MT': (2, 2), 'ND': (3, 2), 'MN': (4, 2),
    'IL': (5, 2), 'MI': (6, 2), 'NY': (8, 2), 'MA': (9, 2), 'CT': (10, 2),
    'OR': (0, 3), 'NV': (1, 3), 'WY': (2, 3), 'SD': (3, 3), 'IA': (4, 3),
    'IN': (5, 3), 'OH': (6, 3), 'PA': (7, 3), 'NJ': (8, 3), 'RI': (9, 3),
    'CA': (0, 4), 'UT': (1, 4), 'CO': (2, 4), 'NE': (3, 4), 'MO': (4, 4),
    'KY': (5, 4), 'WV': (6, 4), 'VA': (7, 4), 'MD': (8, 4), 'DE': (9, 4),
    'AZ': (1, 5), 'NM': (2, 5), 'KS': (3, 5), 'AR': (4, 5), 'TN': (5, 5),
    'NC': (6, 5), 'SC': (7, 5), 'DC': (8, 5),
    'OK': (3, 6), 'LA': (4, 6), 'MS': (5, 6), 'AL': (6, 6), 'GA': (7, 6),
    'HI': (0, 7), 'TX': (3, 7), 'FL': (7, 7),
}


def national_series():
    """Run the national model and return the series used by the time-series plots."""
    params = ModelParams(n_agents=300_000, seed=1870)
    results = simulate(params)
    years = [r.year for r in results]
    populations = [d.total_population for d in DECADE_DATA]
    pct_majority = [r.primary_qualifying_ancestry_share for r in results]
    pct_any = [r.any_qualifying_ancestor_share for r in results]
    pct_not = [1.0 - p for p in pct_majority]
    raw_majority = [pop * pct for pop, pct in zip(populations, pct_majority)]
    raw_not = [pop * pct for pop, pct in zip(populations, pct_not)]
    return years, populations, pct_majority, pct_any, pct_not, raw_majority, raw_not


def fig_pct_over_time(years, pct_majority, pct_any):
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.fill_between(years, [p * 100 for p in pct_majority], 0, color=SUBSTACK_ACCENT, alpha=0.25)
    ax.fill_between(years, [p * 100 for p in pct_any], [p * 100 for p in pct_majority],
                    color=SUBSTACK_GOLD, alpha=0.20)
    ax.fill_between(years, 100, [p * 100 for p in pct_any], color=SUBSTACK_BLUE, alpha=0.20)
    ax.plot(years, [p * 100 for p in pct_majority], color=SUBSTACK_ACCENT, linewidth=2.8,
            marker="o", markersize=6, markeredgecolor="white", markeredgewidth=1.2)
    ax.plot(years, [p * 100 for p in pct_any], color=SUBSTACK_GOLD, linewidth=2.2,
            marker="s", markersize=5, markeredgecolor="white", markeredgewidth=1.0, linestyle="--")

    label_effects = [pe.withStroke(linewidth=4, foreground="white")]
    ax.text(2018, pct_majority[-1] * 50,
            f'Majority "Heritage\nAmerican" (>50%): {pct_majority[-1]:.1%}',
            fontsize=11, fontweight="bold", color=SUBSTACK_ACCENT, ha="right", va="center",
            path_effects=label_effects)
    mid_pct = (pct_majority[-1] + pct_any[-1]) / 2
    ax.text(2018, mid_pct * 100,
            f'Some "Heritage American"\nancestor: {(pct_any[-1] - pct_majority[-1]):.1%}',
            fontsize=11, fontweight="bold", color=SUBSTACK_GOLD, ha="right", va="center",
            path_effects=label_effects)
    pct_no = 1.0 - pct_any[-1]
    top_mid = (pct_any[-1] * 100 + 100) / 2
    ax.text(2018, top_mid, f'No "Heritage American"\nancestor: {pct_no:.1%}',
            fontsize=11, fontweight="bold", color=SUBSTACK_BLUE, ha="right", va="center",
            path_effects=label_effects)

    ax.set_xlim(1870, 2020)
    ax.set_ylim(0, 100)
    ax.yaxis.set_major_formatter(mtick.PercentFormatter())
    ax.set_xlabel("Year", labelpad=2)
    ax.set_ylabel("Share of U.S. Population", labelpad=2)
    ax.set_title('Share of U.S. Population with Pre-1870\nWhite "Heritage American" Ancestry, 1870–2020',
                 fontweight="bold", pad=14)
    ax.grid(axis="y", linestyle="-", linewidth=0.5)
    ax.tick_params(axis="both", pad=2)
    fig.text(0.01, 0.01,
             "Source: Agent-based cohort model; data/national_decade_data.csv (Census, DHS, NHGIS anchors)",
             ha="left", fontsize=8, color=SUBSTACK_MUTED, style="italic")
    plt.tight_layout(pad=0.5)
    plt.subplots_adjust(bottom=0.12)
    plt.savefig(OUT / "pct_white_heritage_over_time.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig_raw_headcount(years, populations, pct_majority, pct_not, raw_majority, raw_not):
    fig, ax = plt.subplots(figsize=(11, 6))
    raw_maj_m = [x / 1e6 for x in raw_majority]
    raw_not_m = [x / 1e6 for x in raw_not]
    pop_m = [x / 1e6 for x in populations]
    ax.stackplot(years, raw_maj_m, raw_not_m, colors=[SUBSTACK_ACCENT, SUBSTACK_BLUE], alpha=0.55,
                 labels=['Majority White "Heritage American"', 'Not majority White "Heritage American"'])
    y_maj = raw_maj_m[-1]
    y_not = raw_not_m[-1]
    ax.annotate(f"{y_maj:.0f}M\n({pct_majority[-1]:.0%})", xy=(2020, y_maj / 2), fontsize=11,
                fontweight="bold", color="white", ha="center",
                path_effects=[pe.withStroke(linewidth=3, foreground=SUBSTACK_ACCENT)])
    ax.annotate(f"{y_not:.0f}M\n({pct_not[-1]:.0%})", xy=(2020, y_maj + y_not / 2), fontsize=11,
                fontweight="bold", color="white", ha="center",
                path_effects=[pe.withStroke(linewidth=3, foreground=SUBSTACK_BLUE)])
    ax.set_xlim(1865, 2030)
    ax.set_ylim(0, max(pop_m) * 1.08)
    ax.yaxis.set_major_formatter(mtick.FuncFormatter(lambda x, _: f"{x:.0f}M"))
    ax.set_xlabel("Census Year")
    ax.set_ylabel("Population (millions)")
    ax.set_title('U.S. Population by White "Heritage American" Ancestry Status, 1870–2020',
                 fontweight="bold", pad=14)
    ax.legend(loc="upper left", frameon=False)
    ax.grid(axis="y", linestyle="-", linewidth=0.5)
    fig.text(0.99, 0.01,
             "Source: Agent-based cohort model; data/national_decade_data.csv (Census totals from NHGIS/Census API)",
             ha="right", fontsize=8, color=SUBSTACK_MUTED, style="italic")
    plt.tight_layout()
    plt.savefig(OUT / "raw_headcount_white_heritage.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def load_state_table():
    """Load committed agent estimates and compute the EC reapportionment columns."""
    df = pd.read_csv(OUT / "state_agent_estimates.csv")
    df["qualifying_pct"] = df["primary_qualifying_ancestry_share"] * 100
    df["counted_population"] = df["population"] * df["primary_qualifying_ancestry_share"]
    state_pops = dict(zip(
        df.loc[df["abbr"] != "DC", "abbr"],
        df.loc[df["abbr"] != "DC", "counted_population"],
    ))
    hyp_house = apportion_house_huntington_hill(state_pops)
    df["actual_ev_2024"] = df["abbr"].map(EV_2024)
    df["hypothetical_house"] = df["abbr"].map(hyp_house).fillna(0).astype(int)
    df["hypothetical_ev"] = df.apply(
        lambda r: 3 if r["abbr"] == "DC" else r["hypothetical_house"] + 2, axis=1)
    df["ev_change"] = df["hypothetical_ev"] - df["actual_ev_2024"]
    return df


def fig_state_map(df_state):
    wha_cmap = LinearSegmentedColormap.from_list(
        "wha", ["#E8DFCE", SUBSTACK_GOLD, SUBSTACK_ACCENT, "#7B2D26"], N=256)
    norm = plt.Normalize(vmin=10, vmax=75)
    fig, ax = plt.subplots(1, 1, figsize=(14, 8))
    ax.set_axis_off()
    for _, row in df_state.iterrows():
        abbr = row["abbr"]
        if abbr not in TILE:
            continue
        col, grow = TILE[abbr]
        pct = row["qualifying_pct"]
        color = wha_cmap(norm(pct))
        rect = FancyBboxPatch((col - 0.45, -grow - 0.45), 0.9, 0.9,
                              boxstyle="round,pad=0.02", facecolor=color,
                              edgecolor="#AEAAA0", linewidth=0.6)
        ax.add_patch(rect)
        fs = 6 if abbr in ("DC", "RI", "DE", "CT", "NJ", "NH", "VT", "MA", "MD") else 7
        ax.annotate(f"{abbr}\n{pct:.0f}%", xy=(col, -grow), ha="center", va="center",
                    fontsize=fs, fontweight="bold", color=SUBSTACK_TEXT,
                    path_effects=[pe.withStroke(linewidth=2, foreground="white")])
    ax.autoscale_view()
    ax.set_aspect("equal")
    ax.margins(0.03)
    sm = plt.cm.ScalarMappable(cmap=wha_cmap, norm=norm)
    sm._A = []
    cbar = fig.colorbar(sm, ax=ax, fraction=0.02, pad=0.02, shrink=0.6)
    cbar.set_label('Majority White "Heritage American" share (%)', fontsize=12)
    cbar.ax.tick_params(labelsize=10)
    cbar.outline.set_edgecolor(SUBSTACK_GRID)
    ax.set_title('Estimated Share of Residents with Majority Pre-1870\nWhite "Heritage American" Ancestry, by State (2020)',
                 fontsize=18, fontweight="bold", pad=16)
    fig.text(0.5, 0.02,
             "Source: State agent-based model; NHGIS historical panel + Census 2020 decennial data",
             ha="center", fontsize=9, color=SUBSTACK_MUTED, style="italic")
    plt.tight_layout()
    plt.savefig(OUT / "map_white_heritage_pct_by_state.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig_ec_cartogram(df_state):
    """Two-panel before->after value cartogram. Each state is a block whose AREA is
    proportional to its electoral votes, stacked into geographic columns (west->east,
    north->south) so the blocks tessellate with no gaps. The left panel shows the
    actual 2024 allocation; the right panel shows the hypothetical allocation under a
    majority pre-1870 White "Heritage American" count. Both panels share one vertical
    scale, so a state visibly shrinks (e.g. CA, FL, NY) or grows (e.g. IN, OH, MO)
    between panels. Color encodes the electoral-vote change in both panels."""
    rows = {r["abbr"]: r for _, r in df_state.iterrows()}
    ev_cmap = LinearSegmentedColormap.from_list(
        "ev_change", [SUBSTACK_BLUE, "#9DBFCC", "#EDE7DC", "#D4956A", SUBSTACK_ACCENT], N=256)
    ev_norm = TwoSlopeNorm(vmin=-25, vcenter=0, vmax=10)

    # Geographic columns from the TILE grid: west (small col) -> east, north -> south.
    cols = {}
    for abbr, (gx, gy) in TILE.items():
        if abbr in rows:
            cols.setdefault(gx, []).append((gy, abbr))
    for gx in cols:
        cols[gx].sort()
    col_ids = sorted(cols)

    UNIT = 0.18   # vertical units per electoral vote (area thus scales with EV)
    WIDTH = 0.86  # block width
    PITCH = 1.0   # column spacing
    GAP = 0.03    # gap between stacked blocks

    def ev_of(abbr, kind):
        r = rows[abbr]
        return int(round(r["actual_ev_2024"] if kind == "actual" else r["hypothetical_ev"]))

    def col_total(gx, kind):
        return sum(ev_of(a, kind) for _, a in cols[gx])

    max_total = max(max(col_total(gx, k) for gx in col_ids)
                    for k in ("actual", "hypothetical"))

    fig, axes = plt.subplots(1, 2, figsize=(17, 13), sharey=True)
    panels = [
        ("actual", "Actual 2024 Electoral College", axes[0]),
        ("hypothetical",
         'Hypothetical: Majority Pre-1870\nWhite "Heritage American" Count', axes[1]),
    ]

    for kind, ptitle, ax in panels:
        ax.set_axis_off()
        ax.set_aspect("equal")
        for j, gx in enumerate(col_ids):
            total = col_total(gx, kind)
            y = total * UNIT   # top of this column; stacks down to a shared baseline at 0
            x = j * PITCH
            for _, abbr in cols[gx]:
                ev = ev_of(abbr, kind)
                change = int(rows[abbr]["ev_change"])
                h = ev * UNIT
                color = ev_cmap(ev_norm(change))
                ax.add_patch(FancyBboxPatch(
                    (x, y - h + GAP / 2.0), WIDTH, h - GAP,
                    boxstyle="round,pad=0,rounding_size=0.05",
                    facecolor=color, edgecolor="white", linewidth=1.1, zorder=2))
                cy = y - h / 2.0
                dark = change <= -14 or change >= 9
                txt = "white" if dark else SUBSTACK_TEXT
                halo = SUBSTACK_TEXT if dark else "white"
                fs = 9.0 if h >= 0.9 else 7.5
                two_line = kind == "hypothetical" and change != 0 and h >= 0.95
                if two_line:
                    ax.text(x + WIDTH / 2.0, cy + 0.18, f"{abbr} {ev}",
                            ha="center", va="center", fontsize=fs, fontweight="bold",
                            color=txt, zorder=4,
                            path_effects=[pe.withStroke(linewidth=2.0, foreground=halo)])
                    ax.text(x + WIDTH / 2.0, cy - 0.18,
                            f"({'+' if change > 0 else ''}{change})",
                            ha="center", va="center", fontsize=fs - 0.5, fontweight="bold",
                            color=txt, zorder=4,
                            path_effects=[pe.withStroke(linewidth=2.0, foreground=halo)])
                else:
                    ax.text(x + WIDTH / 2.0, cy, f"{abbr} {ev}",
                            ha="center", va="center", fontsize=fs, fontweight="bold",
                            color=txt, zorder=4,
                            path_effects=[pe.withStroke(linewidth=2.0, foreground=halo)])
                y -= h
        ax.set_xlim(-0.4, (len(col_ids) - 1) * PITCH + WIDTH + 0.4)
        ax.set_ylim(-0.7, max_total * UNIT + 0.4)
        ax.set_title(ptitle, fontsize=13, fontweight="bold", pad=6)
        ax.text((len(col_ids) - 1) * PITCH / 2.0 + WIDTH / 2.0, -0.55,
                "538 electoral votes", ha="center", va="top",
                fontsize=10, color=SUBSTACK_MUTED, style="italic")

    sm = plt.cm.ScalarMappable(cmap=ev_cmap, norm=ev_norm)
    sm._A = []
    cbar = fig.colorbar(sm, ax=axes, fraction=0.022, pad=0.02, shrink=0.6)
    cbar.set_label("Electoral vote change vs. actual 2024", fontsize=12)
    cbar.ax.tick_params(labelsize=10)
    cbar.outline.set_edgecolor(SUBSTACK_GRID)

    fig.suptitle('U.S. Electoral College: Actual 2024 vs. a Majority Pre-1870 '
                 'White "Heritage American" Count\n(block area = electoral votes)',
                 fontsize=16, fontweight="bold", y=0.995)
    gainers = df_state[df_state["ev_change"] > 0].sort_values("ev_change", ascending=False)
    losers = df_state[df_state["ev_change"] < 0].sort_values("ev_change")
    top_gain = ", ".join(f"{r['abbr']} ({int(r['ev_change']):+d})" for _, r in gainers.head(5).iterrows())
    top_lose = ", ".join(f"{r['abbr']} ({int(r['ev_change']):+d})" for _, r in losers.head(5).iterrows())
    fig.text(0.5, 0.065, f"Biggest gainers: {top_gain}\nBiggest losers: {top_lose}",
             ha="center", fontsize=10, color=SUBSTACK_TEXT, linespacing=1.6, fontweight="bold")
    fig.text(0.5, 0.015,
             "Each block is one state; block area is proportional to its electoral votes, stacked "
             "into geographic columns (west\u2192east).\nHuntington-Hill apportionment, 435 House seats, "
             "DC fixed at 3 EV. Source: state agent-based model with NHGIS historical Census data",
             ha="center", fontsize=8, color=SUBSTACK_MUTED, style="italic")
    plt.subplots_adjust(left=0.02, right=0.9, top=0.9, bottom=0.1, wspace=0.05)
    plt.savefig(OUT / "map_hypothetical_ec_2024_tile_mosaic.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print("Running national model...")
    years, populations, pct_majority, pct_any, pct_not, raw_majority, raw_not = national_series()
    print(f"  2020 majority share: {pct_majority[-1]:.1%}  any-ancestor: {pct_any[-1]:.1%}")

    fig_pct_over_time(years, pct_majority, pct_any)
    fig_raw_headcount(years, populations, pct_majority, pct_not, raw_majority, raw_not)
    print("  wrote pct_white_heritage_over_time.png, raw_headcount_white_heritage.png")

    print("Loading agent estimates + EC reapportionment...")
    df_state = load_state_table()
    print(f"  total hypothetical EV: {int(df_state['hypothetical_ev'].sum())} "
          f"(House excl. DC: {int(df_state.loc[df_state['abbr'] != 'DC', 'hypothetical_house'].sum())})")

    fig_state_map(df_state)
    fig_ec_cartogram(df_state)
    print("  wrote map_white_heritage_pct_by_state.png, map_hypothetical_ec_2024_tile_mosaic.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
