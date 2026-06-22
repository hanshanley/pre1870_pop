#!/usr/bin/env python3
"""
state_pre1870_ancestry_model.py

State-level reduced-form model for estimating the share of current residents whose
ancestry includes, or is primarily from, people living in the United States before
1870.

Interpretation
--------------
The estimates are for CURRENT RESIDENTS OF EACH STATE, not for people whose families
stayed in that state since 1870. Internal migration matters: a person in Arizona may
descend from colonial Virginia, and a person in Massachusetts may have recent
immigrant ancestry.

Definition and scope
--------------------
This reduced-form method (Method A) is an APPROXIMATION of the White Heritage
American share. It targets the same White-only definition as the agent model
(Method B), but does so heuristically: it removes modern Black-alone residents
explicitly and absorbs the remaining non-white / non-old-stock population
(AIAN, Asian, Hispanic-identifying, recent migrants) into the hand-set
per-state ``old_stock_factor`` rather than via an explicit race subtraction.
Because the factor already encodes those populations, this script does NOT add a
separate AIAN/other-race exclusion (doing so would double-count). For the clean,
explicit White-only exclusion use ``state_agent_ancestry_model.py`` (Method B),
which is the method behind the headline state map and EC cartogram.

- Denominator: all current state residents.
- Qualifying ancestry: White U.S. resident source stock present by 1870
  (approximated; see above).
- Excluded ancestry: Black American source stock present by 1870. Modern
  Black-alone residents are assigned zero qualifying pre-1870 ancestry by
  default. Adjustable with --black-exclusion-weight.

The model approximates state-level ancestry shares using:
1. Current foreign-born share by state (immigration-stock proxy).
2. A second-generation proxy inferred from the foreign-born share.
3. Modern Black-alone share by state (exclusion adjustment).
4. A state/region old-stock factor (historical settlement, internal migration,
   and residual non-white / non-old-stock population).
5. A fertility factor (demographic persistence).
6. National calibration anchors from the companion national model.

Data modes
----------
- --download-acs: Fetch live ACS 5-year data from the Census API.
- --use-fallback: Use built-in approximate state priors (no API key needed).
- --state-input-csv: Read custom state inputs from a CSV file.

Usage
-----
    python scripts/state_pre1870_ancestry_model.py --use-fallback --output estimates.csv
    python scripts/state_pre1870_ancestry_model.py --download-acs --output estimates.csv
    python scripts/state_pre1870_ancestry_model.py --use-fallback --sensitivity

Sources
-------
- Census ACS 5-year: B05002 (nativity/foreign-born), B02001 (race).
- Census POP-WP056: Historical race totals, 1790-1990.
- Census POP-WP081: Historical foreign-born population, 1850-2000.
- DHS/OHSS Yearbook Table 1: Long-run LPR admissions.
- Census ACS (2008, 2018) and Haines (HSUS Millennial Ed. 2006): fertility by nativity.

Requires: Python 3.9+. No third-party packages required.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, replace
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


# ── National calibration anchors ────────────────────────────────────────────
# These values come from the companion national agent-based model and serve as
# targets for the state-level calibration step. They ensure that population-
# weighted state averages match the national estimate.

NATIONAL_FOREIGN_BORN_SHARE = 0.146
NATIONAL_SECOND_GEN_SHARE = 0.127
NATIONAL_ONE_NATIVE_PARENT_AMONG_SECOND_GEN = 0.413

DEFAULT_NATIONAL_ANCHORS = {
    "average_qualifying_ancestry": 0.417,
    "any_qualifying_ancestor_share": 0.662,
    "primary_qualifying_ancestry_share": 0.372,
}


# ── Data structures ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class StateInput:
    """Input data for a single state used by the ancestry model.

    Attributes:
        state: Full state name.
        abbr: Two-letter postal abbreviation.
        fips: Two-digit FIPS code (zero-padded).
        population: Total state population.
        foreign_born_share: Fraction of population born outside the U.S.
        black_alone_share: Fraction of population identifying as Black alone.
        old_stock_factor: Subjective multiplier reflecting historical settlement
            depth and internal migration patterns. >1 means more old-stock ancestry
            expected; <1 means less.
        fertility_factor: State-level fertility adjustment (modest effect).
        region: Census region label for reference.
    """
    state: str
    abbr: str
    fips: str
    population: int
    foreign_born_share: float
    black_alone_share: float
    old_stock_factor: float
    fertility_factor: float = 1.0
    region: str = ""


@dataclass(frozen=True)
class StateEstimate:
    """Output estimates for a single state.

    Contains both calibrated (national-anchor-adjusted) and uncalibrated
    versions of the three ancestry metrics.
    """
    state: str
    abbr: str
    fips: str
    population: int
    foreign_born_share: float
    second_generation_proxy: float
    third_plus_proxy: float
    black_alone_share: float
    old_stock_factor: float
    fertility_factor: float
    average_qualifying_ancestry: float
    any_qualifying_ancestor_share: float
    primary_qualifying_ancestry_share: float
    average_qualifying_ancestry_uncalibrated: float
    any_qualifying_ancestor_share_uncalibrated: float
    primary_qualifying_ancestry_share_uncalibrated: float


@dataclass(frozen=True)
class ModelParams:
    """All tunable parameters for the state-level model.

    Defaults represent the central-case assumptions. Most users should only
    need to change the national anchors or black_exclusion_weight.
    """
    # 1.0 = strict exclusion of modern Black-alone from qualifying pool.
    # 0.0 = no exclusion. Values between allow mixed/non-Black lines.
    black_exclusion_weight: float = 1.0

    # "all" = denominator is total population. "nonblack" = denominator is
    # total minus excluded Black share (for non-Black-denominator comparisons).
    denominator: str = "all"

    # Second-generation proxy parameters. The exponent < 1 prevents the proxy
    # from exploding in very high-immigration states.
    second_gen_elasticity: float = 0.70
    second_gen_min: float = 0.015
    second_gen_max: float = 0.330

    # Share of second-generation people with one native-born parent.
    # Higher in low-immigration states, lower in gateway states.
    one_native_parent_national: float = NATIONAL_ONE_NATIVE_PARENT_AMONG_SECOND_GEN
    one_native_parent_elasticity: float = -0.25
    one_native_parent_min: float = 0.250
    one_native_parent_max: float = 0.550

    # Baseline ancestry-metric shares among non-Black third-plus-generation
    # residents in an average state. Adjusted by old_stock_factor and
    # fertility_factor per state.
    base_any_third_plus: float = 0.84
    base_avg_third_plus: float = 0.65
    base_primary_third_plus: float = 0.60

    # Hard bounds to prevent impossible reduced-form outputs
    any_min: float = 0.25
    any_max: float = 0.94
    avg_min: float = 0.10
    avg_max: float = 0.92
    primary_min: float = 0.05
    primary_max: float = 0.90

    # Fertility influence is deliberately small; ancestry differences are driven
    # more by migration and intermarriage than by recent state fertility alone.
    fertility_elasticity: float = 0.25

    # National calibration anchors from the companion national model
    national_avg_anchor: float = DEFAULT_NATIONAL_ANCHORS["average_qualifying_ancestry"]
    national_any_anchor: float = DEFAULT_NATIONAL_ANCHORS["any_qualifying_ancestor_share"]
    national_primary_anchor: float = DEFAULT_NATIONAL_ANCHORS["primary_qualifying_ancestry_share"]


# ── Utility functions ───────────────────────────────────────────────────────

def clip(x: float, lo: float, hi: float) -> float:
    """Clamp x to [lo, hi]."""
    return max(lo, min(hi, x))


def safe_pow(x: float, exponent: float) -> float:
    """Power function that returns 0 for non-positive bases."""
    if x <= 0:
        return 0.0
    return x ** exponent


# ── Fallback state inputs ──────────────────────────────────────────────────
# Approximate priors for offline/dry-run use. For production analysis, use
# --download-acs or provide --state-input-csv with real ACS data.
# The old_stock_factor is the most subjective piece: >1 means deeper historical
# settlement, <1 means more recent population growth from migration.

FALLBACK_STATES: List[StateInput] = [
    StateInput("Alabama", "AL", "01", 5024279, 0.037, 0.260, 0.94, 1.03, "East South Central"),
    StateInput("Alaska", "AK", "02", 733391, 0.080, 0.030, 0.48, 1.07, "Pacific/Noncontiguous"),
    StateInput("Arizona", "AZ", "04", 7151502, 0.135, 0.050, 0.62, 1.06, "Mountain"),
    StateInput("Arkansas", "AR", "05", 3011524, 0.050, 0.150, 1.02, 1.04, "West South Central"),
    StateInput("California", "CA", "06", 39538223, 0.267, 0.055, 0.48, 0.96, "Pacific"),
    StateInput("Colorado", "CO", "08", 5773714, 0.100, 0.040, 0.78, 0.98, "Mountain"),
    StateInput("Connecticut", "CT", "09", 3605944, 0.155, 0.110, 0.92, 0.92, "New England"),
    StateInput("Delaware", "DE", "10", 989948, 0.100, 0.220, 0.88, 0.98, "South Atlantic"),
    StateInput("District of Columbia", "DC", "11", 689545, 0.140, 0.440, 0.55, 0.88, "South Atlantic"),
    StateInput("Florida", "FL", "12", 21538187, 0.210, 0.150, 0.62, 0.92, "South Atlantic"),
    StateInput("Georgia", "GA", "13", 10711908, 0.105, 0.310, 0.80, 1.02, "South Atlantic"),
    StateInput("Hawaii", "HI", "15", 1455271, 0.185, 0.020, 0.30, 1.02, "Pacific/Noncontiguous"),
    StateInput("Idaho", "ID", "16", 1839106, 0.060, 0.010, 0.76, 1.08, "Mountain"),
    StateInput("Illinois", "IL", "17", 12812508, 0.140, 0.140, 0.86, 0.95, "East North Central"),
    StateInput("Indiana", "IN", "18", 6785528, 0.055, 0.095, 1.00, 1.00, "East North Central"),
    StateInput("Iowa", "IA", "19", 3190369, 0.055, 0.040, 1.05, 1.00, "West North Central"),
    StateInput("Kansas", "KS", "20", 2937880, 0.075, 0.060, 0.94, 1.03, "West North Central"),
    StateInput("Kentucky", "KY", "21", 4505836, 0.040, 0.080, 1.10, 1.03, "East South Central"),
    StateInput("Louisiana", "LA", "22", 4657757, 0.045, 0.320, 0.78, 1.02, "West South Central"),
    StateInput("Maine", "ME", "23", 1362359, 0.040, 0.020, 1.16, 0.92, "New England"),
    StateInput("Maryland", "MD", "24", 6177224, 0.155, 0.290, 0.78, 0.96, "South Atlantic"),
    StateInput("Massachusetts", "MA", "25", 7029917, 0.180, 0.075, 0.90, 0.89, "New England"),
    StateInput("Michigan", "MI", "26", 10077331, 0.070, 0.135, 0.95, 0.94, "East North Central"),
    StateInput("Minnesota", "MN", "27", 5706494, 0.090, 0.070, 0.95, 0.98, "West North Central"),
    StateInput("Mississippi", "MS", "28", 2961279, 0.025, 0.370, 0.85, 1.04, "East South Central"),
    StateInput("Missouri", "MO", "29", 6154913, 0.045, 0.115, 1.05, 0.99, "West North Central"),
    StateInput("Montana", "MT", "30", 1084225, 0.025, 0.006, 0.76, 1.02, "Mountain"),
    StateInput("Nebraska", "NE", "31", 1961504, 0.075, 0.050, 0.95, 1.04, "West North Central"),
    StateInput("Nevada", "NV", "32", 3104614, 0.190, 0.090, 0.46, 0.98, "Mountain"),
    StateInput("New Hampshire", "NH", "33", 1377529, 0.065, 0.018, 1.15, 0.90, "New England"),
    StateInput("New Jersey", "NJ", "34", 9288994, 0.235, 0.130, 0.72, 0.95, "Middle Atlantic"),
    StateInput("New Mexico", "NM", "35", 2117522, 0.095, 0.020, 0.52, 1.02, "Mountain"),
    StateInput("New York", "NY", "36", 20201249, 0.225, 0.155, 0.78, 0.92, "Middle Atlantic"),
    StateInput("North Carolina", "NC", "37", 10439388, 0.085, 0.205, 0.90, 1.00, "South Atlantic"),
    StateInput("North Dakota", "ND", "38", 779094, 0.045, 0.035, 0.82, 1.08, "West North Central"),
    StateInput("Ohio", "OH", "39", 11799448, 0.050, 0.120, 1.04, 0.97, "East North Central"),
    StateInput("Oklahoma", "OK", "40", 3959353, 0.060, 0.070, 0.86, 1.06, "West South Central"),
    StateInput("Oregon", "OR", "41", 4237256, 0.100, 0.020, 0.72, 0.92, "Pacific"),
    StateInput("Pennsylvania", "PA", "42", 13002700, 0.075, 0.110, 1.04, 0.94, "Middle Atlantic"),
    StateInput("Rhode Island", "RI", "44", 1097379, 0.145, 0.055, 0.86, 0.90, "New England"),
    StateInput("South Carolina", "SC", "45", 5118425, 0.055, 0.260, 0.86, 1.00, "South Atlantic"),
    StateInput("South Dakota", "SD", "46", 886667, 0.040, 0.025, 0.78, 1.08, "West North Central"),
    StateInput("Tennessee", "TN", "47", 6910840, 0.055, 0.165, 1.04, 1.00, "East South Central"),
    StateInput("Texas", "TX", "48", 29145505, 0.170, 0.120, 0.68, 1.08, "West South Central"),
    StateInput("Utah", "UT", "49", 3271616, 0.090, 0.015, 0.72, 1.18, "Mountain"),
    StateInput("Vermont", "VT", "50", 643077, 0.045, 0.014, 1.18, 0.90, "New England"),
    StateInput("Virginia", "VA", "51", 8631393, 0.125, 0.190, 0.86, 0.98, "South Atlantic"),
    StateInput("Washington", "WA", "53", 7705281, 0.145, 0.040, 0.68, 0.92, "Pacific"),
    StateInput("West Virginia", "WV", "54", 1793716, 0.018, 0.035, 1.18, 0.98, "South Atlantic/Appalachia"),
    StateInput("Wisconsin", "WI", "55", 5893718, 0.055, 0.065, 1.02, 0.95, "East North Central"),
    StateInput("Wyoming", "WY", "56", 576851, 0.035, 0.010, 0.72, 1.05, "Mountain"),
]

STATE_META_BY_FIPS: Dict[str, StateInput] = {s.fips: s for s in FALLBACK_STATES}


# ── Proxy computation ──────────────────────────────────────────────────────

def second_generation_proxy(foreign_born_share: float, params: ModelParams) -> float:
    """Estimate the second-generation (U.S.-born, foreign-born parents) share.

    Uses a power-law relationship anchored to the national foreign-born and
    second-generation shares, with sub-linear elasticity to prevent the proxy
    from exploding in high-immigration states like California.
    """
    ratio = foreign_born_share / NATIONAL_FOREIGN_BORN_SHARE
    raw = NATIONAL_SECOND_GEN_SHARE * safe_pow(ratio, params.second_gen_elasticity)
    # Upper cap also can't exceed 0.95 - fb so first+second gen leave >=5% for the
    # third-plus (old-stock) generation, even in the highest-immigration states.
    return clip(raw, params.second_gen_min, min(params.second_gen_max, 0.95 - foreign_born_share))


def one_native_parent_share(foreign_born_share: float, params: ModelParams) -> float:
    """Estimate the share of second-gen people who have one native-born parent.

    In high-immigration states, second-gen people are more likely to have two
    immigrant parents; in low-immigration states, one native parent is more common.
    The negative elasticity captures this inverse relationship.
    """
    ratio = foreign_born_share / NATIONAL_FOREIGN_BORN_SHARE
    raw = params.one_native_parent_national * safe_pow(ratio, params.one_native_parent_elasticity)
    return clip(raw, params.one_native_parent_min, params.one_native_parent_max)


# ── Core estimation ────────────────────────────────────────────────────────

def raw_state_estimate(inp: StateInput, params: ModelParams) -> StateEstimate:
    """Compute uncalibrated ancestry metrics for a single state.

    The model decomposes the state population into:
    - First generation (foreign-born)
    - Second generation (estimated from foreign-born share)
    - Third-plus generation (remainder)

    Then applies the old-stock factor and fertility factor to estimate what
    fraction of third-plus-generation non-Black residents have qualifying
    pre-1870 ancestry. Second-generation residents with one native parent
    get partial credit.
    """
    # Cap foreign-born share at 0.60: no U.S. state approaches this, so a higher
    # value signals bad input and would break the generational decomposition below.
    fb = clip(inp.foreign_born_share, 0.0, 0.60)
    second = second_generation_proxy(fb, params)
    third_plus = clip(1.0 - fb - second, 0.0, 1.0)

    # Remove modern Black-alone residents from the qualifying ancestry pool
    excluded_black_pool = params.black_exclusion_weight * inp.black_alone_share
    nonblack_third_plus_pool = max(0.0, third_plus - excluded_black_pool)

    if params.denominator == "nonblack":
        denom = max(1e-9, 1.0 - excluded_black_pool)  # 1e-9 floor guards against divide-by-zero
    else:
        denom = 1.0

    # Apply state-specific adjustment factors
    fertility_adj = safe_pow(inp.fertility_factor, params.fertility_elasticity)
    factor = inp.old_stock_factor * fertility_adj

    # Estimate ancestry metrics for third-plus-generation non-Black residents
    any_third = clip(params.base_any_third_plus * factor, params.any_min, params.any_max)
    avg_third = clip(params.base_avg_third_plus * factor, params.avg_min, params.avg_max)
    primary_third = clip(params.base_primary_third_plus * factor, params.primary_min, params.primary_max)

    # Second-generation contribution: only those with one native parent get
    # partial qualifying ancestry (half of the native parent's ancestry share)
    one_native = one_native_parent_share(fb, params)
    second_one_native_pool = second * one_native * max(0.0, 1.0 - excluded_black_pool)

    avg = (nonblack_third_plus_pool * avg_third + second_one_native_pool * 0.5 * avg_third) / denom
    any_share = (nonblack_third_plus_pool * any_third + second_one_native_pool * any_third) / denom
    primary = (nonblack_third_plus_pool * primary_third) / denom

    return StateEstimate(
        state=inp.state,
        abbr=inp.abbr,
        fips=inp.fips,
        population=inp.population,
        foreign_born_share=fb,
        second_generation_proxy=second,
        third_plus_proxy=third_plus,
        black_alone_share=inp.black_alone_share,
        old_stock_factor=inp.old_stock_factor,
        fertility_factor=inp.fertility_factor,
        average_qualifying_ancestry=clip(avg, 0.0, 1.0),
        any_qualifying_ancestor_share=clip(any_share, 0.0, 1.0),
        primary_qualifying_ancestry_share=clip(primary, 0.0, 1.0),
        average_qualifying_ancestry_uncalibrated=clip(avg, 0.0, 1.0),
        any_qualifying_ancestor_share_uncalibrated=clip(any_share, 0.0, 1.0),
        primary_qualifying_ancestry_share_uncalibrated=clip(primary, 0.0, 1.0),
    )


# ── Calibration ─────────────────────────────────────────────────────────────

def weighted_mean(estimates: Sequence[StateEstimate], attr: str) -> float:
    """Compute the population-weighted mean of a StateEstimate attribute."""
    total_pop = sum(e.population for e in estimates)
    return sum(getattr(e, attr) * e.population for e in estimates) / total_pop


def calibrate(estimates: Sequence[StateEstimate], params: ModelParams) -> List[StateEstimate]:
    """Scale state estimates so population-weighted means match national anchors.

    This preserves the relative ranking of states while ensuring the national
    total is consistent with the companion national model's output.
    """
    avg_mean = weighted_mean(estimates, "average_qualifying_ancestry")
    any_mean = weighted_mean(estimates, "any_qualifying_ancestor_share")
    pri_mean = weighted_mean(estimates, "primary_qualifying_ancestry_share")

    avg_mult = params.national_avg_anchor / avg_mean if avg_mean > 0 else 1.0
    any_mult = params.national_any_anchor / any_mean if any_mean > 0 else 1.0
    pri_mult = params.national_primary_anchor / pri_mean if pri_mean > 0 else 1.0

    out = []
    for e in estimates:
        out.append(replace(
            e,
            average_qualifying_ancestry=clip(e.average_qualifying_ancestry * avg_mult, 0.0, 1.0),
            any_qualifying_ancestor_share=clip(e.any_qualifying_ancestor_share * any_mult, 0.0, params.any_max),
            primary_qualifying_ancestry_share=clip(e.primary_qualifying_ancestry_share * pri_mult, 0.0, 1.0),
        ))
    return out


def estimate_states(inputs: Sequence[StateInput], params: ModelParams) -> List[StateEstimate]:
    """Run the full state estimation pipeline: raw estimates then calibration."""
    raw = [raw_state_estimate(inp, params) for inp in inputs]
    return calibrate(raw, params)


# ── Data input functions ───────────────────────────────────────────────────

def fetch_acs_state_inputs(year: int, api_key: Optional[str]) -> List[StateInput]:
    """Fetch population, foreign-born, and Black-alone counts from ACS 5-year.

    Census API variables used:
    - B05002_001E: total population (nativity table universe)
    - B05002_013E: foreign-born population
    - B02001_001E: total population (race table universe)
    - B02001_003E: Black or African American alone
    """
    if not api_key:
        raise RuntimeError(
            "The Census API may require a key. Set CENSUS_API_KEY or pass --api-key. "
            "Alternatively run with --use-fallback or pass --state-input-csv."
        )

    base_url = f"https://api.census.gov/data/{year}/acs/acs5"
    params = {
        "get": "NAME,B05002_001E,B05002_013E,B02001_001E,B02001_003E",
        "for": "state:*",
        "key": api_key,
    }
    url = base_url + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=60) as resp:
        rows = json.loads(resp.read().decode("utf-8"))

    header = rows[0]
    idx = {name: i for i, name in enumerate(header)}
    out: List[StateInput] = []
    for row in rows[1:]:
        fips = row[idx["state"]]
        if fips not in STATE_META_BY_FIPS:
            continue
        meta = STATE_META_BY_FIPS[fips]
        pop_nat = int(float(row[idx["B05002_001E"]]))
        foreign_born = int(float(row[idx["B05002_013E"]]))
        pop_race = int(float(row[idx["B02001_001E"]]))
        black_alone = int(float(row[idx["B02001_003E"]]))
        pop = max(pop_nat, pop_race)
        out.append(StateInput(
            state=meta.state,
            abbr=meta.abbr,
            fips=fips,
            population=pop,
            foreign_born_share=foreign_born / pop_nat if pop_nat else meta.foreign_born_share,
            black_alone_share=black_alone / pop_race if pop_race else meta.black_alone_share,
            old_stock_factor=meta.old_stock_factor,
            fertility_factor=meta.fertility_factor,
            region=meta.region,
        ))
    return sorted(out, key=lambda x: x.state)


def read_state_input_csv(path: str) -> List[StateInput]:
    """Read custom state inputs from a CSV file.

    Required columns: state, abbr, fips, population, foreign_born_share, black_alone_share.
    Optional columns: old_stock_factor, fertility_factor, region.
    Falls back to FALLBACK_STATES metadata for missing optional columns.
    """
    out = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        required = {"state", "abbr", "fips", "population", "foreign_born_share", "black_alone_share"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing required columns in {path}: {sorted(missing)}")
        for row in reader:
            fips = str(row["fips"]).zfill(2)
            meta = STATE_META_BY_FIPS.get(fips)
            out.append(StateInput(
                state=row["state"],
                abbr=row["abbr"],
                fips=fips,
                population=int(float(row["population"])),
                foreign_born_share=float(row["foreign_born_share"]),
                black_alone_share=float(row["black_alone_share"]),
                old_stock_factor=float(row.get("old_stock_factor") or (meta.old_stock_factor if meta else 1.0)),
                fertility_factor=float(row.get("fertility_factor") or (meta.fertility_factor if meta else 1.0)),
                region=row.get("region") or (meta.region if meta else ""),
            ))
    return out


# ── Output functions ───────────────────────────────────────────────────────

def write_estimates_csv(path: str, estimates: Sequence[StateEstimate]) -> None:
    """Write state estimates to a CSV file."""
    fields = list(asdict(estimates[0]).keys()) if estimates else []
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for e in estimates:
            writer.writerow(asdict(e))


def make_sensitivity(estimates_inputs: Sequence[StateInput], base_params: ModelParams) -> List[Dict[str, object]]:
    """Run low/central/high sensitivity scenarios.

    Varies national anchors, Black exclusion weight, second-generation elasticity,
    and old-stock factors to produce a range of plausible estimates.

    The "low"/"high" multipliers are roughly +/-10-15% brackets around each central
    anchor (the larger downward cut on "any"/"primary" reflects their wider
    uncertainty); old_stock_factor is shifted +/-8% and the trailing scalar
    (0.92/1.00/1.08) is the per-scenario old-stock multiplier. Anchors are also
    capped (e.g. 0.90/0.95/0.85) so the high scenario stays demographically possible.
    """
    scenarios = [
        ("low", replace(
            base_params,
            national_avg_anchor=base_params.national_avg_anchor * 0.90,
            national_any_anchor=base_params.national_any_anchor * 0.86,
            national_primary_anchor=base_params.national_primary_anchor * 0.85,
            black_exclusion_weight=min(1.0, base_params.black_exclusion_weight + 0.10),
            second_gen_elasticity=0.80,  # higher elasticity -> more 2nd-gen -> less old-stock
        ), 0.92),
        ("central", base_params, 1.00),
        ("high", replace(
            base_params,
            national_avg_anchor=min(0.90, base_params.national_avg_anchor * 1.12),
            national_any_anchor=min(0.95, base_params.national_any_anchor * 1.14),
            national_primary_anchor=min(0.85, base_params.national_primary_anchor * 1.15),
            black_exclusion_weight=max(0.0, base_params.black_exclusion_weight - 0.10),
            second_gen_elasticity=0.60,  # lower elasticity -> less 2nd-gen -> more old-stock
        ), 1.08),
    ]
    rows: List[Dict[str, object]] = []
    for name, params, old_factor_mult in scenarios:
        shifted_inputs = [replace(s, old_stock_factor=s.old_stock_factor * old_factor_mult) for s in estimates_inputs]
        for e in estimate_states(shifted_inputs, params):
            row = asdict(e)
            row["scenario"] = name
            rows.append(row)
    return rows


def write_sensitivity_csv(path: str, rows: Sequence[Dict[str, object]]) -> None:
    """Write the sensitivity-scenario results to a CSV file."""
    if not rows:
        return
    fields = ["scenario"] + [k for k in rows[0].keys() if k != "scenario"]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def print_preview(estimates: Sequence[StateEstimate], metric: str, n: int = 10) -> None:
    """Print the top and bottom N states by a given metric."""
    print(f"\nTop {n} states by {metric}:")
    for e in sorted(estimates, key=lambda x: getattr(x, metric), reverse=True)[:n]:
        print(f"  {e.abbr:>2} {e.state:<22} {100*getattr(e, metric):5.1f}%")
    print(f"\nBottom {n} states by {metric}:")
    for e in sorted(estimates, key=lambda x: getattr(x, metric))[:n]:
        print(f"  {e.abbr:>2} {e.state:<22} {100*getattr(e, metric):5.1f}%")


# ── CLI ─────────────────────────────────────────────────────────────────────

def build_arg_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the state-level model."""
    p = argparse.ArgumentParser(
        description="Estimate qualifying pre-1870 ancestry by current state of residence."
    )
    source = p.add_mutually_exclusive_group()
    source.add_argument("--download-acs", action="store_true",
                        help="Fetch ACS 5-year state data from the Census API.")
    source.add_argument("--use-fallback", action="store_true",
                        help="Use the built-in fallback state priors (no API key needed).")
    source.add_argument("--state-input-csv",
                        help="Read state input data from a custom CSV file.")
    p.add_argument("--year", type=int, default=2024,
                   help="ACS 5-year vintage to request when using --download-acs (default: 2024).")
    p.add_argument("--api-key", default=os.environ.get("CENSUS_API_KEY"),
                   help="Census API key, or set CENSUS_API_KEY env var.")
    p.add_argument("--output", default="state_pre1870_estimates.csv",
                   help="Output CSV path for central estimates.")
    p.add_argument("--sensitivity", action="store_true",
                   help="Also write a low/central/high sensitivity CSV.")
    p.add_argument("--sensitivity-output", default="state_pre1870_estimates_sensitivity.csv",
                   help="Output CSV path for sensitivity results.")
    p.add_argument("--denominator", choices=["all", "nonblack"], default="all",
                   help="Denominator for ancestry shares (default: all residents).")
    p.add_argument("--black-exclusion-weight", type=float, default=1.0,
                   help="Weight for excluding modern Black-alone from qualifying pool (0-1, default: 1.0).")
    p.add_argument("--national-avg-anchor", type=float,
                   default=DEFAULT_NATIONAL_ANCHORS["average_qualifying_ancestry"],
                   help="National calibration anchor for average qualifying ancestry.")
    p.add_argument("--national-any-anchor", type=float,
                   default=DEFAULT_NATIONAL_ANCHORS["any_qualifying_ancestor_share"],
                   help="National calibration anchor for any-ancestor share.")
    p.add_argument("--national-primary-anchor", type=float,
                   default=DEFAULT_NATIONAL_ANCHORS["primary_qualifying_ancestry_share"],
                   help="National calibration anchor for primary/majority ancestry share.")
    p.add_argument("--preview-metric", default="primary_qualifying_ancestry_share",
                   choices=[
                       "average_qualifying_ancestry",
                       "any_qualifying_ancestor_share",
                       "primary_qualifying_ancestry_share",
                   ],
                   help="Which metric to preview in the top/bottom state listing.")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the state-level ancestry model with the specified parameters."""
    args = build_arg_parser().parse_args(argv)
    params = ModelParams(
        denominator=args.denominator,
        black_exclusion_weight=clip(args.black_exclusion_weight, 0.0, 1.0),
        national_avg_anchor=args.national_avg_anchor,
        national_any_anchor=args.national_any_anchor,
        national_primary_anchor=args.national_primary_anchor,
    )

    try:
        if args.state_input_csv:
            inputs = read_state_input_csv(args.state_input_csv)
        elif args.download_acs:
            inputs = fetch_acs_state_inputs(args.year, args.api_key)
        else:
            inputs = sorted(FALLBACK_STATES, key=lambda x: x.state)
            if not args.use_fallback:
                print("No data source selected; using built-in fallback priors. "
                      "Use --download-acs for ACS data.", file=sys.stderr)

        estimates = estimate_states(inputs, params)
        write_estimates_csv(args.output, estimates)
        print(f"Wrote {len(estimates)} state estimates to {args.output}")
        print_preview(estimates, args.preview_metric)

        national = {
            "average_qualifying_ancestry": weighted_mean(estimates, "average_qualifying_ancestry"),
            "any_qualifying_ancestor_share": weighted_mean(estimates, "any_qualifying_ancestor_share"),
            "primary_qualifying_ancestry_share": weighted_mean(estimates, "primary_qualifying_ancestry_share"),
        }
        print("\nPopulation-weighted national check:")
        for k, v in national.items():
            print(f"  {k}: {100*v:.1f}%")

        if args.sensitivity:
            rows = make_sensitivity(inputs, params)
            write_sensitivity_csv(args.sensitivity_output, rows)
            print(f"\nWrote sensitivity grid to {args.sensitivity_output}")

    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
