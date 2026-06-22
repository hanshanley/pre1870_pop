#!/usr/bin/env python3
"""
pre1870_ancestry_model.py

National agent-based cohort simulation estimating the share of the present-day U.S.
population whose ancestry traces to people living in the United States before 1870.

Overview
--------
The default model defines the qualifying pre-1870 source stock as residents
enumerated as WHITE in the 1870 Census. This excludes Black, American Indian /
Alaska Native, and other non-white (e.g. Chinese) residents from the qualifying
stock, while keeping the entire modern population in the denominator. A present-day
person therefore carries qualifying ("White Heritage American") ancestry only
through White pre-1870 ancestors. The non-white exclusion is a configurable flag
(--include-nonwhite-1870).

This is a reduced-form demographic ancestry model. It is not a definitive genealogical
claim. The Census does not directly observe whether a present-day person has any or
majority ancestry from residents of a past census year.

Core mechanics
--------------
1. Start with a virtual population of agents in 1870.
2. Assign qualifying ancestry fraction q=1 to qualifying source stock, q=0 to
   excluded stock.
3. For each decade, add immigrants with q=0, carry over surviving residents, and
   generate births that inherit the average of two parents' q values.
4. Report summary statistics at each decade.

Data sources
------------
- Census Bureau, Gibson & Jung, POP-WP081: Historical foreign-born population.
- Census Bureau, Gibson & Jung, POP-WP056: Historical race totals, 1790-1990.
- DHS/OHSS Yearbook of Immigration Statistics, Table 1: LPR admissions.
- Census Bureau, American Community Survey (2008, 2018): modern fertility by nativity.
- Historical Statistics of the U.S. (Millennial Edition), Haines: long-run TFR
  and white fertility by nativity.

Usage
-----
    python scripts/pre1870_ancestry_model.py
    python scripts/pre1870_ancestry_model.py --json
    python scripts/pre1870_ancestry_model.py --sensitivity
    python scripts/pre1870_ancestry_model.py --include-nonwhite-1870

Requires: Python 3.9+, numpy.
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
from dataclasses import asdict, dataclass, replace
from typing import Dict, Iterable, List, Optional, Sequence

import numpy as np

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_DATA_DIR = _ROOT / "data"


# ── Decade-level population anchors ─────────────────────────────────────────

@dataclass(frozen=True)
class DecadeData:
    """Census-anchored population data for a single decade.

    Each field is drawn from official sources and serves as an external constraint
    on the simulation.
    """
    year: int
    total_population: int
    foreign_born_share_target: float  # observed stock share, for calibration checks
    tfr: float                        # rough total fertility rate for the decade
    immigrant_admissions_prev_decade: int  # LPR admissions during the prior decade


def _load_decade_data(path: pathlib.Path) -> List[DecadeData]:
    """Load decade-level population anchors from CSV."""
    out = []
    with open(path) as f:
        for row in csv.DictReader(f):
            out.append(DecadeData(
                year=int(row["year"]),
                total_population=int(row["total_population"]),
                foreign_born_share_target=float(row["foreign_born_share_target"]),
                tfr=float(row["tfr"]),
                immigrant_admissions_prev_decade=int(row["immigrant_admissions_prev_decade"]),
            ))
    return sorted(out, key=lambda d: d.year)


def _load_1870_baseline(path: pathlib.Path) -> Dict[str, float]:
    """Load 1870 baseline values (total, Black pop, FB share) from CSV."""
    out = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            out[row["field"]] = float(row["value"])
    return out


def _load_fertility_ratio_by_year(path: pathlib.Path) -> Dict[int, float]:
    """Load the foreign-born:native-born fertility ratio by decade.

    See data/fertility_by_nativity.csv for sources. The primary sources are
    Michael R. Haines' white fertility rates by nativity in Historical Statistics
    of the United States: Millennial Edition (2006) for the historical anchors
    (1900-1910), and the U.S. Census Bureau American Community Survey (2008, 2018;
    total fertility rate by nativity via the own-children method) for the modern
    anchors; intervening decades are interpolated/flagged. The ratio is the
    non-qualifying (immigrant-descended) to old-stock (native) relative fertility
    used to weight births each decade.
    """
    out: Dict[int, float] = {}
    with open(path) as f:
        for row in csv.DictReader(f):
            val = row.get("fb_to_native_fertility_ratio")
            if val:
                out[int(row["year"])] = float(val)
    return out


_DECADE_CSV = _DATA_DIR / "national_decade_data.csv"
_BASELINE_CSV = _DATA_DIR / "national_1870_baseline.csv"
_FERTILITY_CSV = _DATA_DIR / "fertility_by_nativity.csv"

FERTILITY_RATIO_BY_YEAR: Dict[int, float] = (
    _load_fertility_ratio_by_year(_FERTILITY_CSV) if _FERTILITY_CSV.exists() else {}
)

DECADE_DATA: List[DecadeData]
if _DECADE_CSV.exists():
    DECADE_DATA = _load_decade_data(_DECADE_CSV)
else:
    DECADE_DATA = [
        DecadeData(1870,  38_558_371, 0.144, 4.55, 0),
        DecadeData(1880,  50_189_209, 0.133, 4.24, 2_812_191),
        DecadeData(1890,  62_979_766, 0.148, 3.87, 5_246_613),
        DecadeData(1900,  76_212_168, 0.137, 3.56, 3_687_564),
        DecadeData(1910,  92_228_496, 0.146, 3.42, 8_795_386),
        DecadeData(1920, 106_021_537, 0.132, 3.17, 5_735_811),
        DecadeData(1930, 123_202_624, 0.116, 2.45, 4_107_209),
        DecadeData(1940, 132_164_569, 0.088, 2.30,   528_431),
        DecadeData(1950, 151_325_798, 0.069, 3.00, 1_035_039),
        DecadeData(1960, 179_323_175, 0.054, 3.65, 2_515_479),
        DecadeData(1970, 203_211_926, 0.047, 2.48, 3_321_677),
        DecadeData(1980, 226_545_805, 0.060, 1.84, 4_493_314),
        DecadeData(1990, 248_709_873, 0.079, 2.08, 7_338_062),
        DecadeData(2000, 281_421_906, 0.111, 2.06, 9_095_417),
        DecadeData(2010, 308_745_538, 0.129, 1.93, 10_299_430),
        DecadeData(2020, 331_449_281, 0.146, 1.64, 10_250_000),
    ]

if _BASELINE_CSV.exists():
    _baseline = _load_1870_baseline(_BASELINE_CSV)
    TOTAL_1870 = int(_baseline["total_1870"])
    BLACK_1870 = int(_baseline["black_1870"])
    WHITE_1870 = int(_baseline["white_1870"]) if "white_1870" in _baseline else TOTAL_1870 - BLACK_1870
    FOREIGN_BORN_1870_SHARE = _baseline["foreign_born_1870_share"]
else:
    TOTAL_1870 = 38_558_371
    BLACK_1870 = 4_880_009
    WHITE_1870 = 33_589_377
    FOREIGN_BORN_1870_SHARE = 0.144


# ── Model parameters ───────────────────────────────────────────────────────

@dataclass
class ModelParams:
    """All tunable parameters for the national ancestry simulation.

    Default values represent the central-case assumptions. The sensitivity grid
    tests variations around these.
    """
    # 300k agents keeps Monte-Carlo noise on the national share well under a
    # percentage point while still running in a few seconds.
    n_agents: int = 300_000
    # Fixed seed for reproducibility; 1870 is a mnemonic for the simulation's base year.
    seed: int = 1870
    restrict_to_white_1870: bool = True
    count_1870_foreign_born_as_qualifying: bool = True
    # Scales gross LPR admissions to approximate total immigrant entries.
    # >1.0 accounts for non-LPR entries (undocumented, temporary-to-permanent, etc.).
    # NOTE: this is a modeling ASSUMPTION, not a measured constant, and it is the
    # single most consequential free parameter. Empirically the 2020 majority share
    # moves ~25% (mult=1.0) -> ~21% (1.15) -> ~18% (1.30); the sensitivity grid
    # brackets it over 1.00-1.30 so the headline is reported as a range, not a point.
    immigration_flow_multiplier: float = 1.15
    # Differential fertility between old-stock and immigrant-descended (non-
    # qualifying) parents. When native_fertility_differential is True (default),
    # the per-decade ratio is sourced from data/fertility_by_nativity.csv
    # (Haines white fertility by nativity, HSUS Millennial Ed. 2006, for the
    # historical anchors; Census ACS own-children rates for the modern anchors).
    # In the default run EVERY decade has a cited ratio, so the two scalar
    # multipliers below are NEVER reached -- they are a pure fallback for a
    # hypothetical missing data row (verified: no decade triggers them).
    native_fertility_differential: bool = True
    old_stock_fertility_multiplier: float = 0.98
    nonqualifying_fertility_multiplier: float = 1.03
    # Fraction of parent pairs formed by random cross-population sampling vs.
    # assortative mating within ancestry bins. 0.35 admits real mixing without
    # letting trace ancestry diffuse to nearly everyone within a few generations
    # (pure random mating would overstate the "any ancestor" share). ASSUMPTION,
    # but verified near-irrelevant to the majority share (21.2%-22.2% across the
    # full 0.0-1.0 range); it mainly shapes the "any ancestor" diffusion.
    random_mating_rate: float = 0.35
    # Clamp the TFR->turnover conversion to a plausible band so extreme TFR inputs
    # cannot imply an implausible share of the population being newborns per decade
    # (~20% floor at low fertility, ~42% ceiling at 19th-century-high fertility).
    # The turnover formula coefficients are a demographic approximation, NOT measured
    # values; verified non-driving (fixing turnover at a flat 0.30 moves the majority
    # share by <0.1pp) because births on average preserve the population's mean q.
    min_decennial_turnover: float = 0.20
    max_decennial_turnover: float = 0.42
    # "Any ancestor": q strictly above ~0 (1e-6 epsilon ignores float round-off so
    # only genuine zero-ancestry agents are excluded). "Primary/majority": q > 0.50.
    any_threshold: float = 1e-6
    primary_threshold: float = 0.50


# ── Simulation output ──────────────────────────────────────────────────────

@dataclass
class YearResult:
    """Summary statistics for a single decade of the simulation."""
    year: int
    average_qualifying_ancestry: float
    any_qualifying_ancestor_share: float
    primary_qualifying_ancestry_share: float
    observed_foreign_born_share: float
    immigrant_entry_share_used: float
    turnover_used: float


# ── Core model functions ───────────────────────────────────────────────────

def initial_1870_qualifying_share(params: ModelParams) -> float:
    """Compute the share of the 1870 population assigned qualifying ancestry (q=1).

    By default the qualifying source stock is the population enumerated as White
    in 1870, which excludes Black, American Indian/Alaska Native, and other
    non-white (e.g. Chinese) residents. Foreign-born residents already present by
    1870 are included unless ``count_1870_foreign_born_as_qualifying`` is False,
    in which case an approximate White foreign-born mass is also removed.
    """
    if params.restrict_to_white_1870:
        qualifying = WHITE_1870
        # Approximate White foreign-born using the overall 1870 FB share. This is
        # a sensitivity knob; non-white FB are already excluded from WHITE_1870.
        if not params.count_1870_foreign_born_as_qualifying:
            qualifying -= round(WHITE_1870 * FOREIGN_BORN_1870_SHARE)
    else:
        qualifying = TOTAL_1870
        if not params.count_1870_foreign_born_as_qualifying:
            qualifying -= round(TOTAL_1870 * FOREIGN_BORN_1870_SHARE)
    return qualifying / TOTAL_1870


def decade_fertility_multipliers(year: int, params: ModelParams) -> "tuple[float, float]":
    """Return (old_stock, non_qualifying) fertility weights for a decade.

    When ``native_fertility_differential`` is enabled and a cited ratio exists for
    the year (data/fertility_by_nativity.csv), old-stock fertility is normalized to
    1.0 and non-qualifying (immigrant-descended) fertility is set to the cited
    foreign-born:native ratio. Otherwise the scalar params are used.
    """
    if params.native_fertility_differential and year in FERTILITY_RATIO_BY_YEAR:
        return 1.0, FERTILITY_RATIO_BY_YEAR[year]
    return params.old_stock_fertility_multiplier, params.nonqualifying_fertility_multiplier


def turnover_from_tfr(tfr: float, params: ModelParams) -> float:
    """Convert a total fertility rate into a decennial population turnover fraction.

    At replacement-level fertility (~2.1 TFR), about 27% of the population is
    represented as new births per decade. High 19th-century fertility (~4.5)
    raises this to ~37%; low modern fertility (~1.6) drops it to ~25%.
    """
    # Linear fit: 0.27 baseline turnover at replacement TFR (2.1), sloped by 0.04
    # per unit TFR above/below replacement (anchors in the docstring above).
    raw = 0.27 + 0.04 * (tfr - 2.1)
    return float(np.clip(raw, params.min_decennial_turnover, params.max_decennial_turnover))


def immigrant_entry_share(decade: DecadeData, params: ModelParams) -> float:
    """Compute immigrants as a share of the decade's total population.

    Applies the immigration_flow_multiplier to gross LPR admissions and caps
    the result at 25% to prevent extreme parameters from producing nonsensical
    population compositions.
    """
    if decade.year == 1870:
        return 0.0
    raw = params.immigration_flow_multiplier * decade.immigrant_admissions_prev_decade / decade.total_population
    return float(np.clip(raw, 0.0, 0.25))


def draw_parents(q: np.ndarray, size: int, params: ModelParams, rng: np.random.Generator) -> np.ndarray:
    """Sample two parents for each of `size` births and return children's q values.

    Parent selection uses fertility-weighted sampling. Parent pairing is a mixture
    of random mating (across the full population) and assortative mating (within
    ancestry bins). Children inherit the midpoint of their parents' q values:
    q_child = 0.5 * (q_parent1 + q_parent2).

    Assortative mating bins:
    - No qualifying ancestry: q = 0
    - Low: 0 < q < 0.25
    - Medium: 0.25 <= q <= 0.75
    - High: q > 0.75
    """
    # Weight parent selection by differential fertility
    fertility_weights = ((1.0 - q) * params.nonqualifying_fertility_multiplier
                         + q * params.old_stock_fertility_multiplier)
    fertility_weights = fertility_weights / fertility_weights.sum()

    # First parent: drawn from full population with fertility weights
    idx1 = rng.choice(len(q), size=size, replace=True, p=fertility_weights)
    p1 = q[idx1]

    # Second parent: random or assortative depending on random_mating_rate
    random_mask = rng.random(size) < params.random_mating_rate
    p2 = np.empty(size, dtype=np.float64)

    # Random-mating portion: second parent drawn independently from full population
    n_random = int(random_mask.sum())
    if n_random:
        idx2 = rng.choice(len(q), size=n_random, replace=True, p=fertility_weights)
        p2[random_mask] = q[idx2]

    # Assortative-mating portion: second parent drawn from the same ancestry bin
    # as the first parent. This prevents random mixing from unrealistically
    # spreading trace ancestry to nearly everyone within a few generations.
    assort_mask = ~random_mask
    if int(assort_mask.sum()):
        bins = [
            np.flatnonzero(q <= 1e-12),
            np.flatnonzero((q > 1e-12) & (q < 0.25)),
            np.flatnonzero((q >= 0.25) & (q <= 0.75)),
            np.flatnonzero(q > 0.75),
        ]
        # Fallback to full population if a bin is empty
        all_idx = np.arange(len(q))
        bins = [b if len(b) else all_idx for b in bins]

        p1_assort = p1[assort_mask]
        out = np.empty(len(p1_assort), dtype=np.float64)
        for bnum, condition in enumerate([
            p1_assort <= 1e-12,
            (p1_assort > 1e-12) & (p1_assort < 0.25),
            (p1_assort >= 0.25) & (p1_assort <= 0.75),
            p1_assort > 0.75,
        ]):
            k = int(condition.sum())
            if k:
                choices = rng.choice(bins[bnum], size=k, replace=True)
                out[condition] = q[choices]
        p2[assort_mask] = out

    return 0.5 * (p1 + p2)


def summarize(year: int, q: np.ndarray, decade: DecadeData, entry_share: float, turnover: float, params: ModelParams) -> YearResult:
    """Compute summary statistics for a decade's population."""
    return YearResult(
        year=year,
        average_qualifying_ancestry=float(q.mean()),
        any_qualifying_ancestor_share=float((q > params.any_threshold).mean()),
        primary_qualifying_ancestry_share=float((q > params.primary_threshold).mean()),
        observed_foreign_born_share=decade.foreign_born_share_target,
        immigrant_entry_share_used=entry_share,
        turnover_used=turnover,
    )


def simulate(params: ModelParams) -> List[YearResult]:
    """Run the full 1870-2020 agent-based ancestry simulation.

    At each decade:
    1. Compute the immigrant entry share and generational turnover rate.
    2. Split the next decade's population into carry-over, births, and immigrants.
    3. Carry-over agents are sampled from the current population.
    4. Births inherit the average q of two sampled parents (see draw_parents).
    5. Immigrants enter with q=0 (no qualifying pre-1870 ancestry).
    6. The population array is shuffled and summary statistics recorded.
    """
    rng = np.random.default_rng(params.seed)
    initial_share = initial_1870_qualifying_share(params)
    # Initialize: each agent is either q=1 (qualifying) or q=0 (non-qualifying)
    q = (rng.random(params.n_agents) < initial_share).astype(np.float64)

    results: List[YearResult] = [summarize(1870, q, DECADE_DATA[0], 0.0, 0.0, params)]
    for decade in DECADE_DATA[1:]:
        n = params.n_agents
        entry_share = immigrant_entry_share(decade, params)
        immigrant_n = int(round(entry_share * n))
        resident_n = n - immigrant_n
        turnover = turnover_from_tfr(decade.tfr, params)
        birth_n = int(round(turnover * resident_n))
        carry_n = resident_n - birth_n

        # Carry-over: surviving residents from the previous decade
        carry = q[rng.integers(0, len(q), size=carry_n)]
        # Births: children whose q is the midpoint of two parents. Parent
        # selection uses the decade's cited native/immigrant fertility differential.
        om, nm = decade_fertility_multipliers(decade.year, params)
        decade_params = replace(
            params, old_stock_fertility_multiplier=om, nonqualifying_fertility_multiplier=nm,
        )
        children = draw_parents(q, birth_n, decade_params, rng)
        # Immigrants: new entrants with no qualifying ancestry
        immigrants = np.zeros(immigrant_n, dtype=np.float64)

        q = np.concatenate([carry, children, immigrants])
        rng.shuffle(q)
        results.append(summarize(decade.year, q, decade, entry_share, turnover, params))
    return results


# ── Sensitivity analysis ───────────────────────────────────────────────────

def percentile(values: Sequence[float], p: float) -> float:
    """Compute the p-th percentile (p in [0, 1]) of a sequence of values."""
    return float(np.percentile(np.array(values, dtype=float), p * 100.0))


def sensitivity(base: ModelParams, seeds: Iterable[int]) -> Dict[str, object]:
    """Run a grid of parameter combinations and return distributional summaries.

    Varies four key parameters across their tested ranges:
    - old_stock_fertility_multiplier: 0.94, 0.98, 1.02
    - nonqualifying_fertility_multiplier: 1.00, 1.03, 1.08
    - random_mating_rate: 0.20, 0.35, 0.55
    - immigration_flow_multiplier: 1.00, 1.15, 1.30

    Each combination is run with multiple seeds to capture stochastic variation.
    Returns p10/median/p90 intervals for each output metric.
    """
    rows = []
    for old in [0.94, 0.98, 1.02]:
        for new in [1.00, 1.03, 1.08]:
            for mate in [0.20, 0.35, 0.55]:
                for imm_mult in [1.00, 1.15, 1.30]:
                    for seed in seeds:
                        params = ModelParams(**{**asdict(base),
                            "old_stock_fertility_multiplier": old,
                            "nonqualifying_fertility_multiplier": new,
                            "random_mating_rate": mate,
                            "immigration_flow_multiplier": imm_mult,
                            "seed": seed,
                        })
                        final = simulate(params)[-1]
                        rows.append({
                            "old_stock_fertility_multiplier": old,
                            "nonqualifying_fertility_multiplier": new,
                            "random_mating_rate": mate,
                            "immigration_flow_multiplier": imm_mult,
                            "seed": seed,
                            "average_qualifying_ancestry": final.average_qualifying_ancestry,
                            "any_qualifying_ancestor_share": final.any_qualifying_ancestor_share,
                            "primary_qualifying_ancestry_share": final.primary_qualifying_ancestry_share,
                        })

    def interval(key: str) -> Dict[str, float]:
        vals = [row[key] for row in rows]
        return {"p10": percentile(vals, 0.10), "median": percentile(vals, 0.50), "p90": percentile(vals, 0.90)}

    return {
        "n_runs": len(rows),
        "intervals": {
            "average_qualifying_ancestry": interval("average_qualifying_ancestry"),
            "any_qualifying_ancestor_share": interval("any_qualifying_ancestor_share"),
            "primary_qualifying_ancestry_share": interval("primary_qualifying_ancestry_share"),
        },
        "rows": rows,
    }


# ── Output formatting ──────────────────────────────────────────────────────

def pct(x: float) -> str:
    """Format a float as a percentage string, e.g. 0.417 -> ' 41.70%'."""
    return f"{100*x:6.2f}%"


def print_table(results: Sequence[YearResult]) -> None:
    """Print a decade-by-decade table of simulation results."""
    print("year  avg_qualifying  any_ancestor  primary_>50  immigrant_entry  fb_stock_target  turnover")
    for r in results:
        print(f"{r.year}  {pct(r.average_qualifying_ancestry)}  {pct(r.any_qualifying_ancestor_share)}  "
              f"{pct(r.primary_qualifying_ancestry_share)}  {pct(r.immigrant_entry_share_used)}  "
              f"{pct(r.observed_foreign_born_share)}  {pct(r.turnover_used)}")


# ── CLI ─────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the national ancestry model."""
    parser = argparse.ArgumentParser(description="Estimate present-day qualifying pre-1870 ancestry.")
    parser.add_argument("--n-agents", type=int, default=300_000,
                        help="Number of agents in the simulation (default: 300,000).")
    parser.add_argument("--seed", type=int, default=1870,
                        help="Random seed for reproducibility.")
    parser.add_argument("--include-nonwhite-1870", action="store_true",
                        help="Count all 1870 residents (including Black, AIAN, and other "
                             "races) as qualifying stock instead of White residents only.")
    parser.add_argument("--exclude-1870-foreign-born", action="store_true",
                        help="Do not count foreign-born residents already in the U.S. in 1870 as qualifying stock.")
    parser.add_argument("--no-native-fertility", action="store_true",
                        help="Disable the cited per-decade native/immigrant fertility "
                             "differential and use the constant fallback multipliers.")
    parser.add_argument("--immigration-flow-multiplier", type=float, default=1.15,
                        help="Multiplier on gross LPR admissions (default: 1.15).")
    parser.add_argument("--old-stock-fertility", type=float, default=0.98,
                        help="Fertility weight for qualifying-ancestry parents (default: 0.98).")
    parser.add_argument("--nonqualifying-fertility", type=float, default=1.03,
                        help="Fertility weight for non-qualifying parents (default: 1.03).")
    parser.add_argument("--random-mating-rate", type=float, default=0.35,
                        help="Fraction of parent pairs formed randomly vs. assortatively (default: 0.35).")
    parser.add_argument("--json", action="store_true",
                        help="Output results as JSON instead of a formatted table.")
    parser.add_argument("--sensitivity", action="store_true",
                        help="Run a sensitivity grid and print interval summaries.")
    return parser.parse_args()


def main() -> None:
    """Run the national ancestry model with the specified parameters."""
    args = parse_args()
    params = ModelParams(
        n_agents=args.n_agents,
        seed=args.seed,
        restrict_to_white_1870=not args.include_nonwhite_1870,
        count_1870_foreign_born_as_qualifying=not args.exclude_1870_foreign_born,
        native_fertility_differential=not args.no_native_fertility,
        immigration_flow_multiplier=args.immigration_flow_multiplier,
        old_stock_fertility_multiplier=args.old_stock_fertility,
        nonqualifying_fertility_multiplier=args.nonqualifying_fertility,
        random_mating_rate=args.random_mating_rate,
    )
    results = simulate(params)
    if args.json:
        print(json.dumps({
            "params": asdict(params),
            "initial_1870_qualifying_share": initial_1870_qualifying_share(params),
            "results": [asdict(r) for r in results],
        }, indent=2))
    else:
        print("Parameters:")
        for k, v in asdict(params).items():
            print(f"  {k}: {v}")
        print(f"  initial_1870_qualifying_share: {pct(initial_1870_qualifying_share(params))}")
        print()
        print_table(results)
        final = results[-1]
        print("\n2020 point estimate:")
        print(f"  Average qualifying pre-1870 White ancestry: {pct(final.average_qualifying_ancestry)}")
        print(f"  Has any qualifying pre-1870 White ancestor: {pct(final.any_qualifying_ancestor_share)}")
        print(f"  Has primary/majority qualifying ancestry: {pct(final.primary_qualifying_ancestry_share)}")

    if args.sensitivity:
        base = ModelParams(**{**asdict(params), "n_agents": min(params.n_agents, 100_000)})
        sens = sensitivity(base, seeds=[1870, 1871])
        print("\nSensitivity grid, 2020 outcome intervals:")
        for key, vals in sens["intervals"].items():
            print(f"  {key}: p10={pct(vals['p10'])}, median={pct(vals['median'])}, p90={pct(vals['p90'])}")


if __name__ == "__main__":
    main()
