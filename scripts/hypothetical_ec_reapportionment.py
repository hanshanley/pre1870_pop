#!/usr/bin/env python3
"""
hypothetical_ec_reapportionment.py

Reapportion Electoral College votes using a modeled qualifying ancestry population.

Purpose
-------
This script answers a counterfactual question:

    "What would the Electoral College distribution look like if the census only
    counted the modeled qualifying population?"

It does NOT infer party vote choice. It re-apportions the 435 House seats using
the Huntington-Hill (equal-proportions) method, then adds 2 Senate electors per
state. DC is kept at 3 electoral votes by default.

Expected input
--------------
A CSV with at least these columns:

    state, abbr, population,
    primary_qualifying_ancestry_share,
    any_qualifying_ancestor_share,
    average_qualifying_ancestry

Outputs
-------
1. A state-by-state CSV comparing actual 2024 vs. hypothetical electoral votes.
2. An optional interactive HTML choropleth map (requires plotly).
3. A text summary printed to stdout.

Usage
-----
    python scripts/hypothetical_ec_reapportionment.py \\
        --input outputs/state_pre1870_estimates.csv \\
        --metric primary \\
        --output-csv outputs/hypothetical_ec_reapportionment_primary.csv \\
        --output-html outputs/hypothetical_ec_reapportionment_primary_map.html
"""

from __future__ import annotations

import argparse
import heapq
import math
from pathlib import Path
from typing import Dict, Iterable, Tuple

import pandas as pd


# ── 2024 Electoral College baseline ─────────────────────────────────────────
# Based on the 2020 Census apportionment; applies to the 2024 and 2028 elections.

EV_2024: Dict[str, int] = {
    "AL": 9, "AK": 3, "AZ": 11, "AR": 6, "CA": 54,
    "CO": 10, "CT": 7, "DE": 3, "DC": 3, "FL": 30,
    "GA": 16, "HI": 4, "ID": 4, "IL": 19, "IN": 11,
    "IA": 6, "KS": 6, "KY": 8, "LA": 8, "ME": 4,
    "MD": 10, "MA": 11, "MI": 15, "MN": 10, "MS": 6,
    "MO": 10, "MT": 4, "NE": 5, "NV": 6, "NH": 4,
    "NJ": 14, "NM": 5, "NY": 28, "NC": 16, "ND": 3,
    "OH": 17, "OK": 7, "OR": 8, "PA": 19, "RI": 4,
    "SC": 9, "SD": 3, "TN": 11, "TX": 40, "UT": 6,
    "VT": 3, "VA": 13, "WA": 12, "WV": 4, "WI": 10,
    "WY": 3,
}


# ── Metric name resolution ─────────────────────────────────────────────────
# Maps user-friendly short names to the actual CSV column names.

METRICS = {
    "primary": "primary_qualifying_ancestry_share",
    "majority": "primary_qualifying_ancestry_share",
    "any": "any_qualifying_ancestor_share",
    "average": "average_qualifying_ancestry",
    "primary_qualifying_ancestry_share": "primary_qualifying_ancestry_share",
    "any_qualifying_ancestor_share": "any_qualifying_ancestor_share",
    "average_qualifying_ancestry": "average_qualifying_ancestry",
}


def normalize_metric(metric: str) -> str:
    """Map a user-friendly metric name to the corresponding input CSV column name."""
    metric_norm = metric.strip().lower()
    if metric_norm not in METRICS:
        allowed = ", ".join(sorted(METRICS))
        raise ValueError(f"Unknown metric '{metric}'. Allowed values: {allowed}")
    return METRICS[metric_norm]


# ── Huntington-Hill apportionment ──────────────────────────────────────────

def apportion_house_huntington_hill(
    populations: Dict[str, float],
    total_house_seats: int = 435,
) -> Dict[str, int]:
    """Allocate House seats using the Huntington-Hill (equal-proportions) method.

    This is the method used by Congress since 1941 for actual apportionment.

    Algorithm:
    1. Give every state one guaranteed seat.
    2. Assign the remaining seats one at a time. Each seat goes to the state
       with the highest priority value: P / sqrt(n * (n+1)), where P is the
       state's population and n is its current seat count.

    Args:
        populations: {state_abbr: apportionment_population} for the 50 states.
            DC is excluded from House apportionment.
        total_house_seats: Number of House seats to allocate (default: 435).

    Returns:
        {state_abbr: allocated_house_seats}
    """
    if len(populations) != 50:
        raise ValueError(f"Expected exactly 50 states, got {len(populations)}.")
    if total_house_seats < 50:
        raise ValueError("total_house_seats must be at least 50.")

    # Step 1: every state gets one guaranteed seat
    seats = {abbr: 1 for abbr in populations}

    # Priority queue (max-heap via negative values)
    heap: list[Tuple[float, str]] = []
    for abbr, pop in populations.items():
        if pop < 0:
            raise ValueError(f"Negative population for {abbr}: {pop}")
        # Priority for going from 1 to 2 seats: P / sqrt(1 * 2)
        priority = pop / math.sqrt(1 * 2)
        heapq.heappush(heap, (-priority, abbr))

    # Step 2: assign remaining 385 seats by priority
    for _ in range(total_house_seats - 50):
        neg_priority, abbr = heapq.heappop(heap)
        seats[abbr] += 1
        n = seats[abbr]
        next_priority = populations[abbr] / math.sqrt(n * (n + 1))
        heapq.heappush(heap, (-next_priority, abbr))

    return seats


# ── Reapportionment table builder ──────────────────────────────────────────

def build_reapportionment_table(
    input_csv: Path,
    metric: str,
    dc_mode: str = "fixed",
) -> pd.DataFrame:
    """Build the state-by-state actual-vs-hypothetical Electoral College table.

    Reads state estimates, computes the counted population as
    population * qualifying_share, runs Huntington-Hill apportionment,
    and produces a comparison table.

    Args:
        input_csv: Path to the state estimates CSV.
        metric: Which qualifying-share column to use for the counted population.
        dc_mode: "fixed" keeps DC at 3 EV; "exclude" omits DC entirely.

    Returns:
        DataFrame with actual and hypothetical EV columns, sorted by hypothetical EV.
    """
    metric_col = normalize_metric(metric)
    df = pd.read_csv(input_csv)

    required = {"state", "abbr", "population", metric_col}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Input CSV is missing required columns: {sorted(missing)}")

    df = df.copy()
    df["abbr"] = df["abbr"].str.upper()

    bad_abbr = sorted(set(df["abbr"]) - set(EV_2024))
    if bad_abbr:
        raise ValueError(f"Unknown state/DC abbreviations in input: {bad_abbr}")

    # Compute the counterfactual "counted population" for apportionment
    df["qualifying_share"] = df[metric_col].clip(lower=0.0, upper=1.0)
    df["counted_population"] = df["population"] * df["qualifying_share"]

    # Apportion only the 50 states (DC is not part of House apportionment)
    state_df = df[df["abbr"] != "DC"].copy()
    pop_for_apportionment = dict(zip(state_df["abbr"], state_df["counted_population"]))
    hypothetical_house = apportion_house_huntington_hill(pop_for_apportionment)

    # Add actual 2024 baseline for comparison
    df["actual_ev_2024"] = df["abbr"].map(EV_2024)
    df["actual_house_2024"] = df.apply(
        lambda r: 0 if r["abbr"] == "DC" else int(r["actual_ev_2024"] - 2),
        axis=1,
    )
    df["hypothetical_house"] = df["abbr"].map(hypothetical_house).fillna(0).astype(int)

    # Compute hypothetical electoral votes (House seats + 2 Senate electors)
    if dc_mode == "fixed":
        df["hypothetical_ev"] = df.apply(
            lambda r: 3 if r["abbr"] == "DC" else int(r["hypothetical_house"] + 2),
            axis=1,
        )
    elif dc_mode == "exclude":
        df = df[df["abbr"] != "DC"].copy()
        df["hypothetical_ev"] = df["hypothetical_house"] + 2
    else:
        raise ValueError("dc_mode must be either 'fixed' or 'exclude'.")

    df["ev_change"] = df["hypothetical_ev"] - df["actual_ev_2024"]
    df["house_change"] = df["hypothetical_house"] - df["actual_house_2024"]
    df["counted_population_share_of_us"] = (
        df["counted_population"] / df["counted_population"].sum()
    )

    ordered_cols = [
        "state", "abbr", "population", "qualifying_share", "counted_population",
        "counted_population_share_of_us",
        "actual_house_2024", "hypothetical_house", "house_change",
        "actual_ev_2024", "hypothetical_ev", "ev_change",
    ]
    extra_cols = [c for c in df.columns if c not in ordered_cols]
    out = df[ordered_cols + extra_cols].sort_values(
        ["hypothetical_ev", "state"], ascending=[False, True]
    )
    return out


# ── Map visualization ──────────────────────────────────────────────────────

def write_plotly_map(df: pd.DataFrame, output_html: Path, metric_label: str) -> None:
    """Write an interactive Plotly choropleth map colored by EV change.

    The map uses a red-blue diverging scale centered at zero, with hover
    data showing actual and hypothetical EVs, qualifying shares, and
    counted populations.
    """
    try:
        import plotly.express as px
    except ImportError as exc:
        raise RuntimeError(
            "Plotly is required to write the HTML map. Install with: pip install plotly"
        ) from exc

    plot_df = df.copy()
    plot_df["qualifying_share_pct"] = 100 * plot_df["qualifying_share"]
    plot_df["counted_population"] = plot_df["counted_population"].round(0).astype(int)

    fig = px.choropleth(
        plot_df,
        locations="abbr",
        locationmode="USA-states",
        scope="usa",
        color="ev_change",
        hover_name="state",
        hover_data={
            "abbr": True,
            "qualifying_share_pct": ":.1f",
            "counted_population": ":,",
            "actual_ev_2024": True,
            "hypothetical_ev": True,
            "ev_change": True,
        },
        color_continuous_scale="RdBu",
        color_continuous_midpoint=0,
        labels={
            "ev_change": "EV change",
            "qualifying_share_pct": "Qualifying share (%)",
            "counted_population": "Counted population",
            "actual_ev_2024": "Actual 2024 EV",
            "hypothetical_ev": "Hypothetical EV",
        },
        title=(
            "Hypothetical Electoral College reapportionment<br>"
            f"<sup>Census counted only: {metric_label}. "
            "House seats reallocated with Huntington-Hill; DC fixed at 3 EV.</sup>"
        ),
    )

    fig.update_layout(
        margin={"r": 20, "t": 80, "l": 20, "b": 20},
        coloraxis_colorbar={"title": "EV change"},
    )

    fig.write_html(output_html, include_plotlyjs=True, full_html=True)


# ── CLI summary ────────────────────────────────────────────────────────────

def print_summary(df: pd.DataFrame, metric_col: str) -> None:
    """Print a compact summary of the reapportionment results."""
    total_actual = int(df["actual_ev_2024"].sum())
    total_hyp = int(df["hypothetical_ev"].sum())
    total_counted_pop = df["counted_population"].sum()

    gainers = df[df["ev_change"] > 0].sort_values("ev_change", ascending=False)
    losers = df[df["ev_change"] < 0].sort_values("ev_change")

    print("\nHypothetical Electoral College reapportionment")
    print("=" * 55)
    print(f"Metric used: {metric_col}")
    print(f"Total counted population: {total_counted_pop:,.0f}")
    print(f"Total actual 2024 EV: {total_actual}")
    print(f"Total hypothetical EV: {total_hyp}")
    print("\nTop EV gainers:")
    for _, r in gainers.head(12).iterrows():
        print(f"  {r['abbr']:>2} {r['state']:<20} {int(r['actual_ev_2024']):>2} -> {int(r['hypothetical_ev']):>2} ({int(r['ev_change']):+d})")

    print("\nTop EV losers:")
    for _, r in losers.head(12).iterrows():
        print(f"  {r['abbr']:>2} {r['state']:<20} {int(r['actual_ev_2024']):>2} -> {int(r['hypothetical_ev']):>2} ({int(r['ev_change']):+d})")


# ── CLI entrypoint ─────────────────────────────────────────────────────────

def main() -> None:
    """Parse arguments and run the reapportionment pipeline."""
    parser = argparse.ArgumentParser(
        description="Reapportion Electoral College votes using modeled qualifying ancestry population."
    )
    parser.add_argument(
        "--input",
        default="state_pre1870_estimates.csv",
        type=Path,
        help="Input state estimates CSV.",
    )
    parser.add_argument(
        "--metric",
        default="primary",
        help=(
            "Which qualifying-population measure to count. "
            "Options: primary/majority, any, average, or exact column name."
        ),
    )
    parser.add_argument(
        "--output-csv",
        default="hypothetical_ec_reapportionment_primary.csv",
        type=Path,
        help="Output CSV path.",
    )
    parser.add_argument(
        "--output-html",
        default=None,
        type=Path,
        help=(
            "Output HTML map path. If omitted, it is derived from --output-csv "
            "(same directory and stem, with a '_map.html' suffix) so each metric "
            "writes its own map instead of overwriting a shared default."
        ),
    )
    parser.add_argument(
        "--no-map",
        action="store_true",
        help="Skip writing the interactive HTML map.",
    )
    parser.add_argument(
        "--dc-mode",
        choices=["fixed", "exclude"],
        default="fixed",
        help="How to treat DC. 'fixed': keep at 3 EV. 'exclude': omit from output.",
    )
    args = parser.parse_args()

    # Derive the HTML map path from the CSV path when not explicitly provided so
    # that, e.g., outputs/..._average.csv -> outputs/..._average_map.html rather
    # than every metric overwriting a single hard-coded default.
    if args.output_html is None:
        args.output_html = args.output_csv.with_name(args.output_csv.stem + "_map.html")

    metric_col = normalize_metric(args.metric)
    df = build_reapportionment_table(args.input, metric_col, dc_mode=args.dc_mode)

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.output_csv, index=False)

    if not args.no_map:
        args.output_html.parent.mkdir(parents=True, exist_ok=True)
        write_plotly_map(df, args.output_html, metric_label=metric_col)

    print_summary(df, metric_col)
    print(f"\nWrote CSV:  {args.output_csv}")
    if not args.no_map:
        print(f"Wrote map:  {args.output_html}")


if __name__ == "__main__":
    main()
