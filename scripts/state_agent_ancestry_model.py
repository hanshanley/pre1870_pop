#!/usr/bin/env python3
"""
state_agent_ancestry_model.py

State-level agent-based ancestry simulation. Extends the national model's
mechanics to run per-state with historical Census data as anchors.

Definition
----------
The qualifying ("White Heritage American") source stock is the population
enumerated as WHITE in the 1870 Census. Black, American Indian/Alaska Native,
and other non-white (e.g. Chinese) 1870 residents are excluded from the source
stock but remain in the modern denominator. The 1870 White share is read from
the NHGIS panel ``white`` column; see ``--include-nonwhite-1870`` for the legacy
non-Black sensitivity variant.

Unlike the reduced-form state model (state_pre1870_ancestry_model.py), this
model does not use hand-set old_stock_factor or fertility_factor values. Instead
it tracks individual agents with ancestry fractions (q values) across states,
using observed state populations, race, and nativity data from the NHGIS
historical panel to anchor immigration and internal migration flows.

Usage
-----
    python scripts/state_agent_ancestry_model.py --output outputs/state_agent_estimates.csv
    python scripts/state_agent_ancestry_model.py --n-agents 500000 --seeds 1870,1871,1872

Requires: Python 3.9+, numpy.
"""

from __future__ import annotations

import argparse
import csv
import pathlib
import sys
from dataclasses import asdict, dataclass, replace
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from pre1870_ancestry_model import (
    DECADE_DATA,
    ModelParams as NationalModelParams,
    draw_parents,
    turnover_from_tfr,
)
from state_pre1870_ancestry_model import StateEstimate

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"


# ── Data loading ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class StateDecadeData:
    year: int
    abbr: str
    total: int
    white: Optional[int]
    black: Optional[int]
    foreign_born: Optional[int]


def load_nhgis_panel(path: pathlib.Path) -> Dict[Tuple[int, str], StateDecadeData]:
    """Load the NHGIS historical state panel CSV."""
    out = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            year = int(row["year"])
            abbr = row["abbr"]
            out[(year, abbr)] = StateDecadeData(
                year=year,
                abbr=abbr,
                total=int(row["total"]),
                white=int(row["white"]) if row.get("white") else None,
                black=int(row["black"]) if row.get("black") else None,
                foreign_born=int(row["foreign_born"]) if row.get("foreign_born") else None,
            )
    return out


def load_modern_census(path: pathlib.Path) -> Dict[Tuple[int, str], StateDecadeData]:
    """Load the modern Census (2000-2020) state race data.

    The 2000/2010 SF1 data uses P003003 labeled as 'black_alone' but for 2000
    the column actually contains a different race category. We use the
    black_alone_share field instead, which is correct for 2020 PL data.
    For 2000/2010, the share values may be unreliable so we only use total_population
    from those years and rely on 2020 for race breakdowns.
    """
    out = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            if row["geo"] != "state":
                continue
            year = int(row["year"])
            abbr = row["abbr"]
            if not abbr:
                continue
            total = int(row["total_population"])
            if year == 2020:
                black = int(row["black_alone"])
            else:
                black = None
            out[(year, abbr)] = StateDecadeData(
                year=year, abbr=abbr, total=total, white=None, black=black, foreign_born=None,
            )
    return out


def build_state_decade_panel(
    nhgis_path: pathlib.Path,
    modern_path: pathlib.Path,
) -> Dict[Tuple[int, str], StateDecadeData]:
    """Merge NHGIS (1790-1990) and modern Census (2000-2020) into one panel."""
    panel = load_nhgis_panel(nhgis_path)
    modern = load_modern_census(modern_path)
    panel.update(modern)
    return panel


# ── Simulation ────────────────────────────────────────────────────────────

ALL_STATES = [
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL",
    "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME",
    "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH",
    "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI",
    "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
]

STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
    "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine",
    "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska",
    "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island",
    "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas",
    "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}

MODERN_FIPS = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06", "CO": "08",
    "CT": "09", "DE": "10", "DC": "11", "FL": "12", "GA": "13", "HI": "15",
    "ID": "16", "IL": "17", "IN": "18", "IA": "19", "KS": "20", "KY": "21",
    "LA": "22", "ME": "23", "MD": "24", "MA": "25", "MI": "26", "MN": "27",
    "MS": "28", "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33",
    "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39",
    "OK": "40", "OR": "41", "PA": "42", "RI": "44", "SC": "45", "SD": "46",
    "TN": "47", "TX": "48", "UT": "49", "VT": "50", "VA": "51", "WA": "53",
    "WV": "54", "WI": "55", "WY": "56",
}


@dataclass
class StateAgentModelParams:
    n_agents: int = 300_000
    seed: int = 1870
    restrict_to_white_1870: bool = True
    immigration_flow_multiplier: float = 1.15
    old_stock_fertility_multiplier: float = 0.98
    nonqualifying_fertility_multiplier: float = 1.03
    random_mating_rate: float = 0.35
    min_decennial_turnover: float = 0.20
    max_decennial_turnover: float = 0.42
    any_threshold: float = 1e-6
    primary_threshold: float = 0.50
    min_agents_per_state: int = 50


def get_state_pop_target(
    panel: Dict[Tuple[int, str], StateDecadeData], year: int, abbr: str
) -> Optional[int]:
    key = (year, abbr)
    if key in panel:
        return panel[key].total
    return None


def get_state_black_share(
    panel: Dict[Tuple[int, str], StateDecadeData], year: int, abbr: str
) -> float:
    key = (year, abbr)
    if key in panel and panel[key].black is not None and panel[key].total > 0:
        return panel[key].black / panel[key].total
    return 0.0


def get_state_white_share(
    panel: Dict[Tuple[int, str], StateDecadeData], year: int, abbr: str
) -> Optional[float]:
    """Share of a state's population enumerated as White in a given year.

    Returns None when no enumerated White count is available, so callers can
    fall back to a non-Black approximation.
    """
    key = (year, abbr)
    if key in panel and panel[key].white is not None and panel[key].total > 0:
        return panel[key].white / panel[key].total
    return None


def get_state_fb_share(
    panel: Dict[Tuple[int, str], StateDecadeData], year: int, abbr: str
) -> float:
    key = (year, abbr)
    if key in panel and panel[key].foreign_born is not None and panel[key].total > 0:
        return panel[key].foreign_born / panel[key].total
    return 0.0


def allocate_agents_to_states(
    n_agents: int,
    state_pops: Dict[str, int],
    min_per_state: int,
) -> Dict[str, int]:
    """Distribute agents across states proportional to population, with a minimum."""
    total_pop = sum(state_pops.values())
    if total_pop == 0:
        return {}

    n_states = len(state_pops)
    effective_min = min(min_per_state, n_agents // max(n_states, 1))

    alloc = {}
    for abbr in sorted(state_pops):
        raw = max(effective_min, round(n_agents * state_pops[abbr] / total_pop))
        alloc[abbr] = raw

    # Scale to match target exactly
    current_total = sum(alloc.values())
    if current_total != n_agents and current_total > 0:
        diff = n_agents - current_total
        largest = max(alloc, key=lambda s: state_pops.get(s, 0))
        alloc[largest] = max(effective_min, alloc[largest] + diff)

    return alloc


def simulate_states(
    params: StateAgentModelParams,
    panel: Dict[Tuple[int, str], StateDecadeData],
) -> List[StateEstimate]:
    """Run the state-level agent-based simulation from 1870 to 2020."""

    rng = np.random.default_rng(params.seed)
    nat_params = NationalModelParams(
        old_stock_fertility_multiplier=params.old_stock_fertility_multiplier,
        nonqualifying_fertility_multiplier=params.nonqualifying_fertility_multiplier,
        random_mating_rate=params.random_mating_rate,
        immigration_flow_multiplier=params.immigration_flow_multiplier,
    )

    # ── Initialize at 1870 ────────────────────────────────────────────────
    states_1870 = [s for s in ALL_STATES if (1870, s) in panel]
    state_pops_1870 = {s: panel[(1870, s)].total for s in states_1870}
    agent_counts = allocate_agents_to_states(
        params.n_agents, state_pops_1870, params.min_agents_per_state,
    )

    # q arrays per state and state assignment array
    q = np.empty(sum(agent_counts.values()), dtype=np.float64)
    state_ids = np.empty(len(q), dtype=np.int32)

    state_to_idx = {s: i for i, s in enumerate(states_1870)}
    idx_to_state = {i: s for s, i in state_to_idx.items()}

    pos = 0
    for abbr in states_1870:
        n = agent_counts[abbr]
        sid = state_to_idx[abbr]

        black_share = get_state_black_share(panel, 1870, abbr)
        fb_share = get_state_fb_share(panel, 1870, abbr)
        white_share = get_state_white_share(panel, 1870, abbr)

        if params.restrict_to_white_1870:
            # White Heritage source stock: only residents enumerated as White in
            # 1870 qualify. This excludes Black, AIAN, and other non-white races.
            # Fall back to the non-Black approximation only if no White count
            # exists for the state-year.
            qualifying_share = white_share if white_share is not None else (1.0 - black_share)
        else:
            qualifying_share = 1.0

        q[pos:pos + n] = (rng.random(n) < qualifying_share).astype(np.float64)
        state_ids[pos:pos + n] = sid
        pos += n

    # ── Decade loop ───────────────────────────────────────────────────────
    decade_data_by_year = {d.year: d for d in DECADE_DATA}

    for decade in DECADE_DATA[1:]:
        year = decade.year
        prev_year = year - 10
        tfr = decade.tfr
        turnover = turnover_from_tfr(tfr, nat_params)

        # Determine which states exist this decade
        active_states = [s for s in ALL_STATES if (year, s) in panel]
        # Register new states
        for s in active_states:
            if s not in state_to_idx:
                new_idx = max(idx_to_state.keys()) + 1 if idx_to_state else 0
                state_to_idx[s] = new_idx
                idx_to_state[new_idx] = s

        # Current state populations from Census
        target_pops = {}
        for s in active_states:
            target_pops[s] = panel[(year, s)].total

        total_target = sum(target_pops.values())
        n_total = len(q)
        if n_total == 0:
            continue

        # Target agent counts per state (including new states)
        target_agents = allocate_agents_to_states(
            n_total, target_pops, params.min_agents_per_state,
        )

        # ── Immigration ───────────────────────────────────────────────
        national_imm_share = (
            params.immigration_flow_multiplier
            * decade.immigrant_admissions_prev_decade
            / decade.total_population
        ) if year > 1870 else 0.0
        national_imm_share = min(national_imm_share, 0.25)

        # Distribute immigrants to states by their foreign-born share increase
        state_fb_weights = {}
        for s in active_states:
            fb_now = get_state_fb_share(panel, year, s)
            fb_prev = get_state_fb_share(panel, prev_year, s)
            state_fb_weights[s] = max(0.0, fb_now * target_pops[s])

        fb_total = sum(state_fb_weights.values())
        if fb_total > 0:
            state_imm_fracs = {s: w / fb_total for s, w in state_fb_weights.items()}
        else:
            state_imm_fracs = {s: target_pops[s] / total_target for s in active_states}

        total_immigrants = int(round(national_imm_share * n_total))

        # ── Process each state: carry-over + births ───────────────────
        new_q_parts = []
        new_sid_parts = []

        for s in active_states:
            sid = state_to_idx[s]
            mask = state_ids == sid
            state_q = q[mask]
            n_state = len(state_q)

            # Immigrants for this state
            n_imm = int(round(total_immigrants * state_imm_fracs.get(s, 0)))

            if n_state == 0:
                # New state — only gets immigrants this decade; migration fills the rest
                if n_imm > 0:
                    new_q_parts.append(np.zeros(n_imm, dtype=np.float64))
                    new_sid_parts.append(np.full(n_imm, sid, dtype=np.int32))
                continue

            n_resident = max(1, target_agents.get(s, n_state) - n_imm)

            n_births = int(round(turnover * n_resident))
            n_carry = n_resident - n_births

            if n_carry > 0 and n_state > 0:
                carry_idx = rng.integers(0, n_state, size=n_carry)
                carry_q = state_q[carry_idx]
            else:
                carry_q = np.array([], dtype=np.float64)

            if n_births > 0 and n_state >= 2:
                children_q = draw_parents(state_q, n_births, nat_params, rng)
            elif n_births > 0:
                children_q = np.full(n_births, state_q.mean() if n_state > 0 else 0.0)
            else:
                children_q = np.array([], dtype=np.float64)

            imm_q = np.zeros(n_imm, dtype=np.float64)

            state_new_q = np.concatenate([carry_q, children_q, imm_q])
            new_q_parts.append(state_new_q)
            new_sid_parts.append(np.full(len(state_new_q), sid, dtype=np.int32))

        # Combine all states
        q = np.concatenate(new_q_parts) if new_q_parts else np.array([], dtype=np.float64)
        state_ids = np.concatenate(new_sid_parts) if new_sid_parts else np.array([], dtype=np.int32)

        # ── Internal migration (rebalancing) ──────────────────────────
        # Compare current agent counts per state to targets
        current_counts = {}
        for s in active_states:
            sid = state_to_idx[s]
            current_counts[s] = int((state_ids == sid).sum())

        # States that have too many agents -> out-migration pool
        out_pool_q = []
        out_pool_indices = []
        for s in active_states:
            sid = state_to_idx[s]
            current = current_counts[s]
            target = target_agents.get(s, current)
            excess = current - target
            if excess > 0:
                state_mask = np.flatnonzero(state_ids == sid)
                to_remove = rng.choice(state_mask, size=min(excess, len(state_mask)), replace=False)
                out_pool_q.append(q[to_remove])
                out_pool_indices.extend(to_remove)

        if out_pool_q:
            out_q = np.concatenate(out_pool_q)
            rng.shuffle(out_q)

            # Remove out-migrants from their original states
            keep_mask = np.ones(len(q), dtype=bool)
            keep_mask[out_pool_indices] = False
            q = q[keep_mask]
            state_ids = state_ids[keep_mask]

            # Distribute out-migrants to states that need more agents
            out_pos = 0
            for s in active_states:
                sid = state_to_idx[s]
                current = int((state_ids == sid).sum())
                target = target_agents.get(s, current)
                deficit = target - current
                if deficit > 0 and out_pos < len(out_q):
                    n_add = min(deficit, len(out_q) - out_pos)
                    q = np.concatenate([q, out_q[out_pos:out_pos + n_add]])
                    state_ids = np.concatenate([
                        state_ids, np.full(n_add, sid, dtype=np.int32)
                    ])
                    out_pos += n_add

        # Fill any remaining deficits by sampling from the national population.
        # This handles new states that need more agents than the out-pool provides.
        if len(q) > 0:
            for s in active_states:
                sid = state_to_idx[s]
                current = int((state_ids == sid).sum())
                target = target_agents.get(s, current)
                deficit = target - current
                if deficit > 0:
                    sampled_q = q[rng.integers(0, len(q), size=deficit)]
                    q = np.concatenate([q, sampled_q])
                    state_ids = np.concatenate([
                        state_ids, np.full(deficit, sid, dtype=np.int32)
                    ])

        # Shuffle within each state
        perm = rng.permutation(len(q))
        q = q[perm]
        state_ids = state_ids[perm]

    # ── Compute final estimates ───────────────────────────────────────────
    estimates = []
    for s in ALL_STATES:
        if s not in state_to_idx:
            continue
        sid = state_to_idx[s]
        mask = state_ids == sid
        state_q = q[mask]

        if len(state_q) == 0:
            continue

        pop_key = (2020, s)
        if pop_key not in panel:
            pop_key = (2010, s)
        if pop_key not in panel:
            continue

        population = panel[pop_key].total
        fb_share = get_state_fb_share(panel, 2020, s) or get_state_fb_share(panel, 2010, s)
        black_share = get_state_black_share(panel, 2020, s) or get_state_black_share(panel, 2010, s)

        avg_q = float(state_q.mean())
        any_share = float((state_q > params.any_threshold).mean())
        primary_share = float((state_q > params.primary_threshold).mean())

        estimates.append(StateEstimate(
            state=STATE_NAMES.get(s, s),
            abbr=s,
            fips=MODERN_FIPS.get(s, ""),
            population=population,
            foreign_born_share=fb_share,
            second_generation_proxy=0.0,
            third_plus_proxy=0.0,
            black_alone_share=black_share,
            old_stock_factor=0.0,
            fertility_factor=0.0,
            average_qualifying_ancestry=avg_q,
            any_qualifying_ancestor_share=any_share,
            primary_qualifying_ancestry_share=primary_share,
            average_qualifying_ancestry_uncalibrated=avg_q,
            any_qualifying_ancestor_share_uncalibrated=any_share,
            primary_qualifying_ancestry_share_uncalibrated=primary_share,
        ))

    return sorted(estimates, key=lambda e: e.abbr)


def weighted_mean(estimates: Sequence[StateEstimate], attr: str) -> float:
    total_pop = sum(e.population for e in estimates)
    return sum(getattr(e, attr) * e.population for e in estimates) / total_pop


def run_multi_seed(
    params: StateAgentModelParams,
    panel: Dict[Tuple[int, str], StateDecadeData],
    seeds: List[int],
) -> List[StateEstimate]:
    """Run multiple seeds and average the ancestry metrics."""
    all_results: Dict[str, List[Dict[str, float]]] = {}
    base_estimates = None

    for seed in seeds:
        p = StateAgentModelParams(**{
            **{k: getattr(params, k) for k in params.__dataclass_fields__},
            "seed": seed,
        })
        estimates = simulate_states(p, panel)
        for e in estimates:
            if e.abbr not in all_results:
                all_results[e.abbr] = []
            all_results[e.abbr].append({
                "average_qualifying_ancestry": e.average_qualifying_ancestry,
                "any_qualifying_ancestor_share": e.any_qualifying_ancestor_share,
                "primary_qualifying_ancestry_share": e.primary_qualifying_ancestry_share,
            })
        if base_estimates is None:
            base_estimates = {e.abbr: e for e in estimates}

    averaged = []
    for abbr, runs in sorted(all_results.items()):
        base = base_estimates[abbr]
        n = len(runs)
        avg_q = sum(r["average_qualifying_ancestry"] for r in runs) / n
        any_q = sum(r["any_qualifying_ancestor_share"] for r in runs) / n
        pri_q = sum(r["primary_qualifying_ancestry_share"] for r in runs) / n

        averaged.append(replace(
            base,
            average_qualifying_ancestry=avg_q,
            any_qualifying_ancestor_share=any_q,
            primary_qualifying_ancestry_share=pri_q,
        ))

    return averaged


# ── Output ────────────────────────────────────────────────────────────────

def write_estimates_csv(path: pathlib.Path, estimates: Sequence[StateEstimate]) -> None:
    fields = list(asdict(estimates[0]).keys()) if estimates else []
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for e in estimates:
            writer.writerow(asdict(e))


def print_preview(estimates: Sequence[StateEstimate]) -> None:
    metric = "primary_qualifying_ancestry_share"
    print(f"\nTop 10 states by {metric}:")
    for e in sorted(estimates, key=lambda x: getattr(x, metric), reverse=True)[:10]:
        print(f"  {e.abbr:>2} {e.state:<22} {100*getattr(e, metric):5.1f}%")
    print(f"\nBottom 10 states by {metric}:")
    for e in sorted(estimates, key=lambda x: getattr(x, metric))[:10]:
        print(f"  {e.abbr:>2} {e.state:<22} {100*getattr(e, metric):5.1f}%")

    print(f"\nPopulation-weighted national check:")
    for attr in ["average_qualifying_ancestry", "any_qualifying_ancestor_share",
                  "primary_qualifying_ancestry_share"]:
        print(f"  {attr}: {100*weighted_mean(estimates, attr):.1f}%")


# ── CLI ───────────────────────────────────────────────────────────────────

def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="State-level agent-based ancestry simulation."
    )
    parser.add_argument("--n-agents", type=int, default=300_000)
    parser.add_argument("--seeds", default="1870",
                        help="Comma-separated seeds for multi-run averaging.")
    parser.add_argument("--output", type=pathlib.Path,
                        default=ROOT / "outputs" / "state_agent_estimates.csv")
    parser.add_argument("--nhgis-panel", type=pathlib.Path,
                        default=DATA_DIR / "nhgis_historical_state_panel_1790_1990.csv")
    parser.add_argument("--modern-census", type=pathlib.Path,
                        default=DATA_DIR / "modern_census_state_race_2000_2020.csv")
    parser.add_argument("--restrict-to-white-1870", action="store_true", default=True,
                        help="Restrict the 1870 source stock to enumerated White "
                             "residents (excludes Black, AIAN, and other races).")
    parser.add_argument("--include-nonwhite-1870", action="store_true",
                        help="Count all 1870 residents regardless of race (Black, "
                             "AIAN, and other races) as qualifying stock, instead of "
                             "White residents only. For sensitivity comparison.")
    args = parser.parse_args(argv)

    nhgis_path = args.nhgis_panel
    modern_path = args.modern_census

    if not nhgis_path.exists():
        print(f"NHGIS panel not found: {nhgis_path}", file=sys.stderr)
        print("Run: python scripts/fetch_nhgis_state_panel.py", file=sys.stderr)
        return 1

    print(f"Loading data...")
    panel = build_state_decade_panel(nhgis_path, modern_path)
    print(f"  Panel: {len(panel)} state-year records")

    seeds = [int(s) for s in args.seeds.split(",")]
    params = StateAgentModelParams(
        n_agents=args.n_agents,
        restrict_to_white_1870=not args.include_nonwhite_1870,
    )

    print(f"Running simulation with {args.n_agents:,} agents, {len(seeds)} seed(s)...")

    if len(seeds) == 1:
        params = StateAgentModelParams(**{
            **{k: getattr(params, k) for k in params.__dataclass_fields__},
            "seed": seeds[0],
        })
        estimates = simulate_states(params, panel)
    else:
        estimates = run_multi_seed(params, panel, seeds)

    write_estimates_csv(args.output, estimates)
    print(f"\nWrote {len(estimates)} state estimates to {args.output}")
    print_preview(estimates)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
