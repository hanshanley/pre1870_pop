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
from matplotlib.patches import FancyBboxPatch, Circle, Rectangle, Patch
from matplotlib.collections import PatchCollection, LineCollection
from matplotlib.patches import Rectangle as MplRectangle

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
OUT = ROOT / "outputs"
DATA = ROOT / "data"

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


def _grow_tilegram(evmap, anchors):
    """Allocate, for each state, a contiguous block of unit cells on a square lattice
    whose size equals the state's electoral votes. Cells are grown outward from a
    geographic seed (the hand-tuned TILE position), with a compactness bias so each
    region stays a tight block. Returns {abbr: [(x, y), ...]}. The result is a square
    tilegram: one box per electoral vote, arranged roughly geographically."""
    def neighbors(cell):
        x, y = cell
        return [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]

    seeds, used = {}, set()
    for a in evmap:
        cell = (round(anchors[a][0]), round(anchors[a][1]))
        while cell in used:
            cell = (cell[0], cell[1] - 1)
        seeds[a] = cell
        used.add(cell)

    claimed, region, remaining, frontier = {}, {a: [] for a in evmap}, {}, {a: [] for a in evmap}
    for a, cell in seeds.items():
        if evmap[a] <= 0:
            remaining[a] = 0
            continue
        claimed[cell] = a
        region[a].append(cell)
        remaining[a] = evmap[a] - 1
        frontier[a] = list(neighbors(cell))

    def d2(c, a):
        sx, sy = seeds[a]
        return (c[0] - sx) ** 2 + (c[1] - sy) ** 2

    active = [a for a in evmap if remaining[a] > 0]
    while active:
        a = min(active, key=lambda s: len(region[s]) / evmap[s])
        cand = [c for c in frontier[a] if c not in claimed]
        if not cand:
            ring = set()
            for c in region[a]:
                ring.update(neighbors(c))
            cand = [c for c in ring if c not in claimed]
            if not cand:
                active.remove(a)
                continue
        rset = set(region[a])
        best = min(cand, key=lambda c: d2(c, a) - 2.5 * sum(n in rset for n in neighbors(c)))
        claimed[best] = a
        region[a].append(best)
        frontier[a] = [c for c in frontier[a] if c not in claimed]
        frontier[a].extend(n for n in neighbors(best) if n not in claimed)
        remaining[a] -= 1
        if remaining[a] <= 0:
            active.remove(a)
    return region


def fig_ec_cartogram(df_state):
    """Side-by-side electoral-college tilegrams ("boxes" cartograms). Each state is
    drawn as a contiguous block of unit squares, one square per electoral vote, with a
    bold outline around each state so individual states stay legible, laid out roughly
    geographically so the whole still reads like a U.S. map. States are colored by
    partisan lean (Republican-leaning red, Democratic-leaning blue, swing/battleground
    neutral). LEFT: the ACTUAL 2024 Electoral College (every U.S. resident counted).
    RIGHT: a HYPOTHETICAL Electoral College in which only the pre-1870 White "Heritage
    American"-descended population is counted. Because one box always equals one
    electoral vote, a state's block visibly shrinks (CA, NY, FL) or grows (IN, OH, MO,
    KY, TN) between the two maps in exact proportion to the seats it loses or gains, and
    the map as a whole shifts visibly toward the Republican-leaning interior."""
    # Partisan lean: swing/battleground states are neutral; the rest split R / D.
    SWING = {"AZ", "GA", "MI", "NV", "NC", "PA", "WI", "NH"}
    DEM = {"CA", "CO", "CT", "DE", "DC", "HI", "IL", "ME", "MD", "MA", "MN",
           "NJ", "NM", "NY", "OR", "RI", "VT", "VA", "WA"}
    LEAN_COLORS = {"R": "#B5402F", "D": "#2C5E7E", "S": "#CFC6B6"}

    def lean(a):
        return "S" if a in SWING else "D" if a in DEM else "R"

    EVA = {r["abbr"]: int(round(r["actual_ev_2024"])) for _, r in df_state.iterrows()}
    EVH = {r["abbr"]: int(round(r["hypothetical_ev"])) for _, r in df_state.iterrows()}

    # Geographic seed positions from the hand-tuned TILE grid (one cell per state),
    # scaled so big states have room to grow; AK/HI dropped into a lower-left inset.
    sp = 3.0
    anchors = {a: (c * sp, -r * sp) for a, (c, r) in TILE.items() if a in EVA}
    anchors["AK"] = (-1.0 * sp, -8.0 * sp)
    anchors["HI"] = (1.5 * sp, -8.0 * sp)

    regA = _grow_tilegram(EVA, anchors)
    regH = _grow_tilegram(EVH, anchors)

    allcells = [c for cells in regA.values() for c in cells] + \
               [c for cells in regH.values() for c in cells]
    xs = [c[0] for c in allcells]
    ys = [c[1] for c in allcells]
    xlim = (min(xs) - 1.0, max(xs) + 1.0)
    ylim = (min(ys) - 1.0, max(ys) + 1.0)

    def state_borders(region):
        owner = {c: a for a, cells in region.items() for c in cells}
        segs = []
        for a, cells in region.items():
            for (x, y) in cells:
                if owner.get((x + 1, y)) != a:
                    segs.append([(x + 0.5, y - 0.5), (x + 0.5, y + 0.5)])
                if owner.get((x - 1, y)) != a:
                    segs.append([(x - 0.5, y - 0.5), (x - 0.5, y + 0.5)])
                if owner.get((x, y + 1)) != a:
                    segs.append([(x - 0.5, y + 0.5), (x + 0.5, y + 0.5)])
                if owner.get((x, y - 1)) != a:
                    segs.append([(x - 0.5, y - 0.5), (x + 0.5, y - 0.5)])
        return segs

    fig, axes = plt.subplots(1, 2, figsize=(20, 9.5))

    def draw(ax, region, evmap, title):
        ax.set_axis_off()
        ax.set_aspect("equal")
        ax.set_xlim(*xlim)
        ax.set_ylim(*ylim)
        # Fully-filled unit cells with a faint internal grid (the "boxes")...
        for a, cells in region.items():
            fc = LEAN_COLORS[lean(a)]
            for (x, y) in cells:
                ax.add_patch(MplRectangle((x - 0.5, y - 0.5), 1.0, 1.0, facecolor=fc,
                                          edgecolor="#FFFFFF", linewidth=0.4, zorder=3))
        # ...then a bold outline around each state so states stay distinct.
        ax.add_collection(LineCollection(state_borders(region), colors="#2B2B2B",
                                         linewidths=1.6, zorder=4))
        for a, cells in region.items():
            if not cells:
                continue
            cx = sum(c[0] for c in cells) / len(cells)
            cy = sum(c[1] for c in cells) / len(cells)
            ev = evmap[a]
            light = lean(a) in ("R", "D")
            txt = "white" if light else SUBSTACK_TEXT
            halo = "#1A1A1A" if light else "white"
            fs = 6.0 if ev <= 3 else (9.0 if ev >= 12 else 7.4)
            ax.text(cx, cy, f"{a}\n{ev}", ha="center", va="center", linespacing=0.9,
                    fontsize=fs, fontweight="bold", color=txt, zorder=5,
                    path_effects=[pe.withStroke(linewidth=1.7, foreground=halo)])
        ax.set_title(title, fontsize=14.5, fontweight="bold", pad=6)

    draw(axes[0], regA, EVA,
         "Actual 2024 Electoral College\n(every U.S. resident counted)")
    draw(axes[1], regH, EVH,
         'If only pre-1870 White "Heritage Americans" counted\n(hypothetical electoral votes)')

    legend_handles = [
        Patch(facecolor=LEAN_COLORS["R"], edgecolor="#2B2B2B", label="Republican-leaning"),
        Patch(facecolor=LEAN_COLORS["S"], edgecolor="#2B2B2B", label="Swing / battleground"),
        Patch(facecolor=LEAN_COLORS["D"], edgecolor="#2B2B2B", label="Democratic-leaning"),
    ]
    fig.legend(handles=legend_handles, loc="lower center", ncol=3, frameon=False,
               fontsize=11, bbox_to_anchor=(0.5, 0.115))

    fig.suptitle('U.S. Electoral College: Actual 2024 vs. a Pre-1870 White "Heritage American" Count',
                 fontsize=17, fontweight="bold", y=0.995)
    gainers = df_state[df_state["ev_change"] > 0].sort_values("ev_change", ascending=False)
    losers = df_state[df_state["ev_change"] < 0].sort_values("ev_change")
    top_gain = ", ".join(f"{r['abbr']} ({int(r['ev_change']):+d})" for _, r in gainers.head(5).iterrows())
    top_lose = ", ".join(f"{r['abbr']} ({int(r['ev_change']):+d})" for _, r in losers.head(5).iterrows())
    fig.text(0.5, 0.075, f"Biggest gainers: {top_gain}     |     Biggest losers: {top_lose}",
             ha="center", fontsize=10.5, color=SUBSTACK_TEXT, fontweight="bold")
    fig.text(0.5, 0.022,
             "Each box = one electoral vote; a state's block shrinks or grows in exact proportion to the "
             "seats it loses or gains between the two maps. Color = partisan lean.\nMajority pre-1870 White "
             "\"Heritage American\" count, Huntington-Hill apportionment, 435 House seats, DC fixed at 3 EV. "
             "Source: state agent-based model with NHGIS historical Census data.",
             ha="center", fontsize=8.5, color=SUBSTACK_MUTED, style="italic", linespacing=1.4)
    plt.subplots_adjust(left=0.02, right=0.98, top=0.85, bottom=0.2, wspace=0.04)
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
