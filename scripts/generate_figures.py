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
from matplotlib.patches import Rectangle as MplRectangle
import geopandas as gpd
from shapely.affinity import scale as aff_scale, translate as aff_translate

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

# Full state name -> postal abbreviation, for joining the GeoJSON to the model output.
NAME2ABBR = {
    'Alabama': 'AL', 'Alaska': 'AK', 'Arizona': 'AZ', 'Arkansas': 'AR', 'California': 'CA',
    'Colorado': 'CO', 'Connecticut': 'CT', 'Delaware': 'DE', 'District of Columbia': 'DC',
    'Florida': 'FL', 'Georgia': 'GA', 'Hawaii': 'HI', 'Idaho': 'ID', 'Illinois': 'IL',
    'Indiana': 'IN', 'Iowa': 'IA', 'Kansas': 'KS', 'Kentucky': 'KY', 'Louisiana': 'LA',
    'Maine': 'ME', 'Maryland': 'MD', 'Massachusetts': 'MA', 'Michigan': 'MI', 'Minnesota': 'MN',
    'Mississippi': 'MS', 'Missouri': 'MO', 'Montana': 'MT', 'Nebraska': 'NE', 'Nevada': 'NV',
    'New Hampshire': 'NH', 'New Jersey': 'NJ', 'New Mexico': 'NM', 'New York': 'NY',
    'North Carolina': 'NC', 'North Dakota': 'ND', 'Ohio': 'OH', 'Oklahoma': 'OK', 'Oregon': 'OR',
    'Pennsylvania': 'PA', 'Rhode Island': 'RI', 'South Carolina': 'SC', 'South Dakota': 'SD',
    'Tennessee': 'TN', 'Texas': 'TX', 'Utah': 'UT', 'Vermont': 'VT', 'Virginia': 'VA',
    'Washington': 'WA', 'West Virginia': 'WV', 'Wisconsin': 'WI', 'Wyoming': 'WY',
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
    """Side-by-side electoral-college value cartograms. LEFT: the ACTUAL 2024
    Electoral College, with every state scaled about its own centroid so its area is
    proportional to its real electoral votes. RIGHT: a HYPOTHETICAL Electoral College
    in which only the pre-1870 White "Heritage American"-descended population is
    counted, with each state scaled to its hypothetical electoral votes and colored by
    the change vs. 2024. Both panels share one area-per-electoral-vote scale and the
    same axis limits, so a state's size is directly comparable between the two maps:
    states that shrink from left to right (e.g. CA, NY, FL) lose seats, states that
    grow (e.g. IN, OH, MO) gain them."""
    ev_cmap = LinearSegmentedColormap.from_list(
        "ev_change", [SUBSTACK_BLUE, "#9DBFCC", "#EDE7DC", "#D4956A", SUBSTACK_ACCENT], N=256)
    ev_norm = TwoSlopeNorm(vmin=-25, vcenter=0, vmax=10)
    NEUTRAL = "#8FAAB8"

    evd = {r["abbr"]: r for _, r in df_state.iterrows()}
    base = gpd.read_file(DATA / "us_states.geojson").to_crs(5070)
    base["abbr"] = base["name"].map(NAME2ABBR)
    base = base[base["abbr"].notna() & base["abbr"].isin(evd)].copy()
    base["actual"] = base["abbr"].map(lambda a: int(round(evd[a]["actual_ev_2024"])))
    base["hyp"] = base["abbr"].map(lambda a: int(round(evd[a]["hypothetical_ev"])))
    base["change"] = base["abbr"].map(lambda a: int(evd[a]["ev_change"]))
    base["area"] = base.geometry.area

    # One area-per-EV scale, shared by both panels. Actual and hypothetical electoral
    # votes both sum to 538 (535 excluding DC), so the same scale makes the two maps
    # directly comparable. DC is drawn separately as a fixed offset marker.
    main = base[base["abbr"] != "DC"]
    per_ev = main["area"].sum() / main["actual"].sum()

    def build(ev_attr):
        gg = base.copy()
        geoms = []
        for r in gg.itertuples():
            s = np.sqrt((getattr(r, ev_attr) * per_ev) / r.area)
            geoms.append(aff_scale(r.geometry, xfact=s, yfact=s, origin=r.geometry.centroid))
        gg = gg.set_geometry(gpd.GeoSeries(geoms, index=gg.index, crs=gg.crs))
        conus = gg[~gg["abbr"].isin(["AK", "HI", "DC"])]
        minx, miny, maxx, maxy = conus.total_bounds
        gname = gg.geometry.name

        def reposition(abbr, fx, fy, shrink=1.0):
            geom = gg.loc[gg["abbr"] == abbr, gname].iloc[0]
            if shrink != 1.0:
                geom = aff_scale(geom, shrink, shrink, origin=geom.centroid)
            c = geom.centroid
            tx, ty = minx + fx * (maxx - minx), miny + fy * (maxy - miny)
            gg.loc[gg["abbr"] == abbr, gname] = aff_translate(geom, tx - c.x, ty - c.y)

        reposition("AK", 0.05, 0.10, shrink=0.45)
        reposition("HI", 0.15, 0.02)
        return gg

    gA = build("actual")
    gH = build("hyp")
    gname = gA.geometry.name

    minx, miny, maxx, maxy = pd.concat([gA, gH]).total_bounds
    padx, pady = (maxx - minx) * 0.03, (maxy - miny) * 0.05

    fig, axes = plt.subplots(1, 2, figsize=(20, 9.5))

    def draw(ax, gg, ev_attr, color_mode, title):
        ax.set_axis_off()
        ax.set_aspect("equal")
        ax.set_xlim(minx - padx, maxx + padx)
        ax.set_ylim(miny - pady, maxy + pady)
        for r in gg.itertuples():
            if r.abbr == "DC":
                continue
            fc = NEUTRAL if color_mode == "neutral" else ev_cmap(ev_norm(r.change))
            gpd.GeoSeries([getattr(r, gname)]).plot(
                ax=ax, facecolor=fc, edgecolor="white", linewidth=0.8, zorder=3, alpha=0.95)
        for r in gg.itertuples():
            if r.abbr == "DC":
                continue
            ev = getattr(r, ev_attr)
            c = getattr(r, gname).centroid
            dark = color_mode == "change" and (r.change <= -14 or r.change >= 9)
            txt = "white" if dark else SUBSTACK_TEXT
            halo = SUBSTACK_TEXT if dark else "white"
            small = ev <= 4
            fs = 6.0 if small else (9.5 if ev >= 10 else 7.4)
            lab = f"{r.abbr} {ev}" if small else f"{r.abbr}\n{ev}"
            ax.text(c.x, c.y, lab, ha="center", va="center", linespacing=0.95,
                    fontsize=fs, fontweight="bold", color=txt, zorder=5,
                    path_effects=[pe.withStroke(linewidth=1.8, foreground=halo)])
        # DC: fixed offset square (3 EV in both scenarios) with a leader line.
        dc = gg[gg["abbr"] == "DC"].iloc[0]
        dcc = dc.geometry.centroid
        sz = np.sqrt(3 * per_ev)
        fc = NEUTRAL if color_mode == "neutral" else ev_cmap(ev_norm(int(dc["change"])))
        ax.add_patch(MplRectangle(
            (dcc.x - sz / 2, dcc.y - sz / 2), sz, sz,
            facecolor=fc, edgecolor="white", linewidth=0.8, zorder=4))
        ax.annotate(f"DC {int(getattr(dc, ev_attr))}", xy=(dcc.x, dcc.y),
                    xytext=(dcc.x + 300000, dcc.y - 150000),
                    fontsize=6.5, fontweight="bold", color=SUBSTACK_TEXT, zorder=6,
                    arrowprops=dict(arrowstyle="-", color=SUBSTACK_MUTED, lw=0.6),
                    path_effects=[pe.withStroke(linewidth=2, foreground="white")])
        ax.set_title(title, fontsize=14.5, fontweight="bold", pad=6)

    draw(axes[0], gA, "actual", "neutral",
         "Actual 2024 Electoral College\n(every U.S. resident counted)")
    draw(axes[1], gH, "hyp", "change",
         'If only pre-1870 White "Heritage Americans" counted\n(hypothetical electoral votes)')

    sm = plt.cm.ScalarMappable(cmap=ev_cmap, norm=ev_norm)
    sm._A = []
    cax = fig.add_axes([0.36, 0.135, 0.28, 0.018])
    cbar = fig.colorbar(sm, cax=cax, orientation="horizontal")
    cbar.set_label("Electoral-vote change vs. actual 2024 (right panel)", fontsize=10)
    cbar.ax.tick_params(labelsize=9)
    cbar.outline.set_edgecolor(SUBSTACK_GRID)

    fig.suptitle('U.S. Electoral College: Actual 2024 vs. a Pre-1870 White "Heritage American" Count',
                 fontsize=17, fontweight="bold", y=0.995)
    gainers = df_state[df_state["ev_change"] > 0].sort_values("ev_change", ascending=False)
    losers = df_state[df_state["ev_change"] < 0].sort_values("ev_change")
    top_gain = ", ".join(f"{r['abbr']} ({int(r['ev_change']):+d})" for _, r in gainers.head(5).iterrows())
    top_lose = ", ".join(f"{r['abbr']} ({int(r['ev_change']):+d})" for _, r in losers.head(5).iterrows())
    fig.text(0.5, 0.075, f"Biggest gainers: {top_gain}     |     Biggest losers: {top_lose}",
             ha="center", fontsize=10.5, color=SUBSTACK_TEXT, fontweight="bold")
    fig.text(0.5, 0.022,
             "Each state's area is proportional to its electoral votes on a single shared scale; the two maps "
             "are directly comparable.\nMajority pre-1870 White \"Heritage American\" count, Huntington-Hill "
             "apportionment, 435 House seats, DC fixed at 3 EV. Source: state agent-based model with NHGIS "
             "historical Census data.",
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
