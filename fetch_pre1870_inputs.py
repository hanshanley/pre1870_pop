#!/usr/bin/env python3
"""
fetch_pre1870_inputs.py

Fetch and cache the data needed for the census-anchored pre-1870 ancestry stock model
and hypothetical Electoral College reapportionment.

This is a data acquisition layer, not the final model. It creates standardized CSVs
that the modeling scripts can consume.

Main data products
------------------
data/modern_census_state_race_2000_2020.csv
    State-level total, Black-alone, and American Indian/Alaska Native-alone counts
    from the Census API for 2000, 2010, and 2020.

data/modern_census_us_race_2000_2020.csv
    National total, Black-alone, and AIAN-alone counts from the Census API.

data/dhs_lpr_by_decade.csv
    Gross lawful permanent resident admissions by decade, 1820-2010s,
    entered from DHS Yearbook Table 1 style totals used by the model.

data/state_fips_2024_electoral_votes.csv
    State FIPS, abbreviations, and 2024 electoral vote baseline.

data/source_manifest.csv
    Source/field documentation.

Optional historical inputs
--------------------------
For historical state/race/nativity data from 1790-1990, use NHGIS. Because NHGIS
extract table names/column names depend on the extract, the most robust workflow is:

1. Create/export NHGIS state-level tables for total population, race, foreign-born,
   and nativity/parentage where available.
2. Save a cleaned CSV to:
       data/nhgis_historical_state_panel_1790_1990.csv
   with columns:
       year,state,abbr,total,black,aian,foreign_born,native_parentage
   Missing columns are allowed if unavailable, but year/state/abbr/total are required.

Usage
-----
    # Write static inputs (no API key needed)
    python fetch_pre1870_inputs.py --write-static --validate

    # Fetch modern Census data (requires API key)
    export CENSUS_API_KEY="YOUR_KEY"
    python fetch_pre1870_inputs.py --fetch-modern-census --validate

    # Show Census API query templates (key redacted)
    python fetch_pre1870_inputs.py --show-queries
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import pathlib
import re
from typing import List, Tuple

try:
    import requests
except ImportError as exc:
    raise SystemExit("Install requests first: pip install requests") from exc


# ── Paths ────────────────────────────────────────────────────────────────────

ROOT = pathlib.Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / "census_cache"
DATA_DIR.mkdir(exist_ok=True)
CACHE_DIR.mkdir(exist_ok=True)

CENSUS_API_KEY = os.environ.get("CENSUS_API_KEY", "")


# ── Census API variable mapping ─────────────────────────────────────────────
# The Census changed variable naming between the 2000/2010 SF1 releases and
# the 2020 PL 94-171 redistricting file.
#
# 2020 PL 94-171:
#   P1_001N = total population
#   P1_004N = Black or African American alone
#   P1_005N = American Indian and Alaska Native alone
#
# 2000/2010 SF1:
#   P001001 = total population
#   P003003 = Black or African American alone
#   P003004 = American Indian and Alaska Native alone

CENSUS_API = {
    2000: {
        "dataset": "dec/sf1",
        "total": "P001001",
        "black": "P003003",
        "aian": "P003004",
    },
    2010: {
        "dataset": "dec/sf1",
        "total": "P001001",
        "black": "P003003",
        "aian": "P003004",
    },
    2020: {
        "dataset": "dec/pl",
        "total": "P1_001N",
        "black": "P1_004N",
        "aian": "P1_005N",
    },
}


# ── State FIPS codes ────────────────────────────────────────────────────────
# (FIPS code, postal abbreviation, full name) for 50 states + DC.

STATE_FIPS = [
    ("01", "AL", "Alabama"), ("02", "AK", "Alaska"), ("04", "AZ", "Arizona"),
    ("05", "AR", "Arkansas"), ("06", "CA", "California"), ("08", "CO", "Colorado"),
    ("09", "CT", "Connecticut"), ("10", "DE", "Delaware"), ("11", "DC", "District of Columbia"),
    ("12", "FL", "Florida"), ("13", "GA", "Georgia"), ("15", "HI", "Hawaii"),
    ("16", "ID", "Idaho"), ("17", "IL", "Illinois"), ("18", "IN", "Indiana"),
    ("19", "IA", "Iowa"), ("20", "KS", "Kansas"), ("21", "KY", "Kentucky"),
    ("22", "LA", "Louisiana"), ("23", "ME", "Maine"), ("24", "MD", "Maryland"),
    ("25", "MA", "Massachusetts"), ("26", "MI", "Michigan"), ("27", "MN", "Minnesota"),
    ("28", "MS", "Mississippi"), ("29", "MO", "Missouri"), ("30", "MT", "Montana"),
    ("31", "NE", "Nebraska"), ("32", "NV", "Nevada"), ("33", "NH", "New Hampshire"),
    ("34", "NJ", "New Jersey"), ("35", "NM", "New Mexico"), ("36", "NY", "New York"),
    ("37", "NC", "North Carolina"), ("38", "ND", "North Dakota"), ("39", "OH", "Ohio"),
    ("40", "OK", "Oklahoma"), ("41", "OR", "Oregon"), ("42", "PA", "Pennsylvania"),
    ("44", "RI", "Rhode Island"), ("45", "SC", "South Carolina"), ("46", "SD", "South Dakota"),
    ("47", "TN", "Tennessee"), ("48", "TX", "Texas"), ("49", "UT", "Utah"),
    ("50", "VT", "Vermont"), ("51", "VA", "Virginia"), ("53", "WA", "Washington"),
    ("54", "WV", "West Virginia"), ("55", "WI", "Wisconsin"), ("56", "WY", "Wyoming"),
]


# ── 2024 Electoral College baseline ─────────────────────────────────────────
# Based on the 2020 Census apportionment; applies to 2024 and 2028 elections.

EV_2024 = {
    "AL": 9, "AK": 3, "AZ": 11, "AR": 6, "CA": 54, "CO": 10, "CT": 7, "DE": 3,
    "DC": 3, "FL": 30, "GA": 16, "HI": 4, "ID": 4, "IL": 19, "IN": 11, "IA": 6,
    "KS": 6, "KY": 8, "LA": 8, "ME": 4, "MD": 10, "MA": 11, "MI": 15, "MN": 10,
    "MS": 6, "MO": 10, "MT": 4, "NE": 5, "NV": 6, "NH": 4, "NJ": 14, "NM": 5,
    "NY": 28, "NC": 16, "ND": 3, "OH": 17, "OK": 7, "OR": 8, "PA": 19, "RI": 4,
    "SC": 9, "SD": 3, "TN": 11, "TX": 40, "UT": 6, "VT": 3, "VA": 13, "WA": 12,
    "WV": 4, "WI": 10, "WY": 3,
}


# ── Historical LPR admissions ───────────────────────────────────────────────
# Gross lawful permanent resident admissions by decade (persons).
# Source: DHS/OHSS Yearbook of Immigration Statistics, Table 1.
# Pre-1820 values are zero because systematic immigration records begin in 1820.

DHS_LPR_BY_DECADE = {
    1790: 0, 1800: 0, 1810: 0, 1820: 129_000, 1830: 538_000, 1840: 1_427_000,
    1850: 2_815_000, 1860: 2_082_000, 1870: 2_742_000, 1880: 5_249_000,
    1890: 3_694_000, 1900: 8_202_000, 1910: 6_347_000, 1920: 4_296_000,
    1930: 699_000, 1940: 857_000, 1950: 2_499_000, 1960: 3_214_000,
    1970: 4_493_000, 1980: 7_338_000, 1990: 9_095_000, 2000: 10_299_000,
    2010: 10_000_000,
}


# ── Utility functions ───────────────────────────────────────────────────────

def now_utc() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def cache_path(name: str) -> pathlib.Path:
    """Return the path for a named cache file in the census_cache/ directory."""
    return CACHE_DIR / name


def sanitize_url(url: str) -> str:
    """Remove API key values from a URL before logging or raising errors."""
    return re.sub(r"([?&]key=)[^&]+", r"\\1<REDACTED>", url)


# ── Census API fetch/parse ──────────────────────────────────────────────────

def request_json(url: str, cache_name: str, force: bool = False) -> list:
    """Fetch JSON from a URL, caching the response to disk.

    If a cached file exists and force=False, the cached copy is returned without
    making a network request. This avoids repeated API calls during development.
    """
    cache = cache_path(cache_name)
    if cache.exists() and not force:
        return json.loads(cache.read_text())
    if not CENSUS_API_KEY:
        raise SystemExit(
            "CENSUS_API_KEY is required for Census API calls. "
            "Set it with: export CENSUS_API_KEY='your_key'"
        )
    try:
        r = requests.get(url, timeout=90)
    except requests.RequestException as exc:
        raise SystemExit(
            "Census API request failed. This is usually a network/DNS issue or a blocked "
            f"connection. URL: {sanitize_url(url)}\nError: {exc}"
        ) from exc
    if r.status_code >= 400:
        raise SystemExit(
            f"Census API error {r.status_code}: {r.text[:500]}\nURL: {sanitize_url(url)}"
        )
    data = r.json()
    cache.write_text(json.dumps(data, indent=2))
    return data


def census_api_url(year: int, geo: str) -> Tuple[str, List[str]]:
    """Build the Census API URL and variable list for a given year and geography.

    Args:
        year: Census year (2000, 2010, or 2020).
        geo: "us" for national totals, "state" for state-level data.

    Returns:
        A tuple of (url, list_of_requested_variables).
    """
    spec = CENSUS_API[year]
    variables = ["NAME", spec["total"], spec["black"], spec["aian"]]
    forclause = "us:1" if geo == "us" else "state:*"
    url = (
        f"https://api.census.gov/data/{year}/{spec['dataset']}"
        f"?get={','.join(variables)}&for={forclause}&key={CENSUS_API_KEY}"
    )
    return url, variables


def parse_census_api_response(year: int, geo: str, data: list) -> list[dict]:
    """Parse raw Census API JSON into a list of row dicts.

    The Census API returns a list-of-lists where the first row is the header.
    This function converts each data row into a dict with standardized field
    names (total_population, black_alone, aian_alone, etc.) and computes
    population shares.
    """
    spec = CENSUS_API[year]
    header, rows = data[0], data[1:]
    total_var, black_var, aian_var = spec["total"], spec["black"], spec["aian"]

    out = []
    for row in rows:
        rec = dict(zip(header, row))
        state_fips = rec.get("state", "00" if geo == "us" else "")
        abbr = ""
        if geo == "state":
            abbr_lookup = {fips: abbr for fips, abbr, _ in STATE_FIPS}
            abbr = abbr_lookup.get(state_fips, "")
        elif geo == "us":
            abbr = "US"

        total = int(rec[total_var])
        black = int(rec[black_var])
        aian = int(rec[aian_var])
        out.append({
            "year": year,
            "geo": geo,
            "state_fips": state_fips,
            "abbr": abbr,
            "name": rec["NAME"],
            "total_population": total,
            "black_alone": black,
            "aian_alone": aian,
            "black_alone_share": black / total if total else None,
            "aian_alone_share": aian / total if total else None,
            "dataset": spec["dataset"],
            "total_variable": total_var,
            "black_variable": black_var,
            "aian_variable": aian_var,
            "retrieved_at_utc": now_utc(),
        })
    return out


# ── CSV writer ──────────────────────────────────────────────────────────────

def write_csv(path: pathlib.Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    """Write a list of dicts to a CSV file.

    If rows is empty and fieldnames is provided, writes a header-only CSV.
    Creates parent directories as needed.
    """
    path.parent.mkdir(exist_ok=True, parents=True)
    if not rows:
        if fieldnames is None:
            raise ValueError("No rows and no fieldnames")
        path.write_text(",".join(fieldnames) + "\n")
        return
    if fieldnames is None:
        fieldnames = list(rows[0].keys())
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


# ── Main data operations ───────────────────────────────────────────────────

def fetch_modern_census(force: bool = False) -> None:
    """Fetch 2000/2010/2020 decennial Census data from the API.

    Queries both national and state-level geographies for each year and writes
    two output CSVs: one for state-level data and one for national totals.
    Results are cached as JSON in census_cache/ to avoid redundant API calls.
    """
    state_rows = []
    us_rows = []
    for year in sorted(CENSUS_API):
        for geo in ["us", "state"]:
            url, _vars = census_api_url(year, geo)
            data = request_json(url, f"census_{year}_{geo}.json", force=force)
            rows = parse_census_api_response(year, geo, data)
            if geo == "us":
                us_rows.extend(rows)
            else:
                state_rows.extend(rows)

    fields = [
        "year", "geo", "state_fips", "abbr", "name",
        "total_population", "black_alone", "aian_alone",
        "black_alone_share", "aian_alone_share",
        "dataset", "total_variable", "black_variable", "aian_variable",
        "retrieved_at_utc",
    ]
    write_csv(DATA_DIR / "modern_census_state_race_2000_2020.csv", state_rows, fields)
    write_csv(DATA_DIR / "modern_census_us_race_2000_2020.csv", us_rows, fields)


def write_static_inputs() -> None:
    """Write static model inputs that do not require API access.

    Produces:
    - state_fips_2024_electoral_votes.csv: FIPS codes and 2024 EV baseline.
    - dhs_lpr_by_decade.csv: Historical LPR admissions series.
    - source_manifest.csv: Documentation of all data sources.
    - native_correction_notes.csv: Notes on Native American under-enumeration.
    """
    # Electoral vote / FIPS reference table
    rows = []
    for fips, abbr, name in STATE_FIPS:
        rows.append({
            "state_fips": fips,
            "abbr": abbr,
            "state": name,
            "actual_ev_2024": EV_2024[abbr],
            # DC has 3 electoral votes but zero House seats
            "actual_house_2024": 0 if abbr == "DC" else EV_2024[abbr] - 2,
        })
    write_csv(DATA_DIR / "state_fips_2024_electoral_votes.csv", rows)

    # Immigration admissions time series
    immigration_rows = []
    for decade, admissions in sorted(DHS_LPR_BY_DECADE.items()):
        immigration_rows.append({
            "decade": decade,
            "gross_lpr_admissions": admissions,
            "source": "DHS/OHSS Yearbook of Immigration Statistics Table 1",
            "source_url": "https://ohss.dhs.gov/topics/immigration/yearbook/2023/table1",
            "notes": "Static model input; update from source if DHS revises table or newer yearbook is desired.",
        })
    write_csv(DATA_DIR / "dhs_lpr_by_decade.csv", immigration_rows)

    # Source manifest: tracks provenance for every dataset the model consumes
    manifest_rows = [
        {
            "dataset": "Modern decennial state/national race counts",
            "needed_for": "2000/2010/2020 anchors for total, Black-alone, AIAN-alone population",
            "source": "U.S. Census Bureau API",
            "source_url": "https://www.census.gov/data/developers/data-sets/decennial-census.html",
            "status": "fetched_by_script_with_CENSUS_API_KEY",
            "output_file": "data/modern_census_state_race_2000_2020.csv; data/modern_census_us_race_2000_2020.csv",
        },
        {
            "dataset": "Historical state/national population by race, 1790-1990",
            "needed_for": "pre-1870 resident stock and state apportionment inputs",
            "source": "Census POP-WP056 / IPUMS NHGIS",
            "source_url": "https://www.census.gov/library/working-papers/2002/demo/POP-twps0056.html",
            "status": "requires_NHGIS_or_manual_cleaned_CSV",
            "output_file": "data/nhgis_historical_state_panel_1790_1990.csv",
        },
        {
            "dataset": "NHGIS historical decennial tables",
            "needed_for": "state-level total, race, foreign-born, nativity/parentage where available",
            "source": "IPUMS NHGIS",
            "source_url": "https://www.nhgis.org/data-availability",
            "status": "requires_NHGIS_account/API_key_or_manual_export",
            "output_file": "data/nhgis_historical_state_panel_1790_1990.csv",
        },
        {
            "dataset": "Lawful permanent resident admissions",
            "needed_for": "immigration-entry cohorts by decade",
            "source": "DHS/OHSS Yearbook of Immigration Statistics Table 1",
            "source_url": "https://ohss.dhs.gov/topics/immigration/yearbook/2023/table1",
            "status": "static_csv_written_by_script",
            "output_file": "data/dhs_lpr_by_decade.csv",
        },
        {
            "dataset": "American Indian taxed/untaxed enumeration notes",
            "needed_for": "Native under-enumeration correction/sensitivity",
            "source": "1890 Census Report on Indians; Census history page",
            "source_url": "https://www.census.gov/library/publications/1894/dec/volume-10.html",
            "status": "source_manifest_only; correction module still needs extraction/cleaning",
            "output_file": "data/native_correction_notes.csv",
        },
        {
            "dataset": "2024 Electoral College baseline",
            "needed_for": "actual 2024 EV comparison",
            "source": "National Archives Electoral College allocation",
            "source_url": "https://www.archives.gov/electoral-college/allocation",
            "status": "static_csv_written_by_script",
            "output_file": "data/state_fips_2024_electoral_votes.csv",
        },
    ]
    write_csv(DATA_DIR / "source_manifest.csv", manifest_rows)

    # Native American enumeration notes
    native_rows = [
        {
            "topic": "Native enumeration caveat",
            "description": "Many Native Americans were not counted in early censuses if classified as Indians not taxed; use a sensitivity/correction rather than treating the 1870 enumerated AIAN count as complete.",
            "source": "National Archives Prologue article",
            "source_url": "https://www.archives.gov/publications/prologue/2006/summer/indian-census.html",
        },
        {
            "topic": "1890 Indian report",
            "description": "1890 Census produced a report on Indians taxed and not taxed; useful for a backcast correction by state/territory.",
            "source": "Census 1890 Volume 10 Report on Indians",
            "source_url": "https://www.census.gov/library/publications/1894/dec/volume-10.html",
        },
        {
            "topic": "Census history page",
            "description": "Census Bureau notes 1890 effort to count all Indians, both taxed and untaxed.",
            "source": "Census Bureau Censuses of American Indians",
            "source_url": "https://www.census.gov/about/history/census-records-family-history/census-records/censuses-of-american-indians.html",
        },
    ]
    write_csv(DATA_DIR / "native_correction_notes.csv", native_rows)


def show_census_queries() -> None:
    """Print Census API query templates with the API key redacted.

    Useful for documentation or for running queries manually in a browser.
    """
    for year in sorted(CENSUS_API):
        for geo in ["us", "state"]:
            spec = CENSUS_API[year]
            variables = ["NAME", spec["total"], spec["black"], spec["aian"]]
            forclause = "us:1" if geo == "us" else "state:*"
            url = (
                f"https://api.census.gov/data/{year}/{spec['dataset']}"
                f"?get={','.join(variables)}&for={forclause}&key=<YOUR_KEY>"
            )
            print(f"{year} {geo}: {url}")


def validate_outputs() -> None:
    """Run lightweight validation checks on written outputs.

    Checks:
    - 2024 electoral votes sum to 538 (50 states + DC).
    - Electoral vote file has exactly 51 rows (50 states + DC).
    - DHS LPR file is non-empty.
    """
    problems = []

    ev_path = DATA_DIR / "state_fips_2024_electoral_votes.csv"
    if ev_path.exists():
        with ev_path.open() as f:
            rows = list(csv.DictReader(f))
        ev_sum = sum(int(r["actual_ev_2024"]) for r in rows)
        if ev_sum != 538:
            problems.append(f"2024 EV sum should be 538, got {ev_sum}")
        if len(rows) != 51:
            problems.append(f"EV file should have 50 states + DC, got {len(rows)} rows")

    lpr_path = DATA_DIR / "dhs_lpr_by_decade.csv"
    if lpr_path.exists():
        with lpr_path.open() as f:
            rows = list(csv.DictReader(f))
        if not rows:
            problems.append("DHS LPR file has no rows")

    if problems:
        raise SystemExit("Validation failed:\n" + "\n".join(f"- {p}" for p in problems))
    print("Validation OK.")


# ── CLI entrypoint ──────────────────────────────────────────────────────────

def main() -> None:
    """Parse command-line arguments and run the requested operations."""
    p = argparse.ArgumentParser(
        description="Fetch and write data inputs for the pre-1870 ancestry stock model."
    )
    p.add_argument("--fetch-modern-census", action="store_true",
                   help="Fetch 2000/2010/2020 total, Black-alone, AIAN-alone counts from Census API.")
    p.add_argument("--write-static", action="store_true",
                   help="Write static inputs: DHS decade immigration, 2024 EV/FIPS, source manifest.")
    p.add_argument("--force", action="store_true",
                   help="Refetch Census API JSON even when cache exists.")
    p.add_argument("--validate", action="store_true", help="Run lightweight validation checks.")
    p.add_argument("--show-queries", action="store_true",
                   help="Print the Census API query templates without exposing your real key.")
    args = p.parse_args()

    if args.show_queries:
        show_census_queries()

    if args.write_static:
        write_static_inputs()
        print(f"Wrote static inputs to {DATA_DIR}")

    if args.fetch_modern_census:
        fetch_modern_census(force=args.force)
        print(f"Wrote modern Census API outputs to {DATA_DIR}")

    if args.validate:
        validate_outputs()

    if not args.write_static and not args.fetch_modern_census and not args.validate and not args.show_queries:
        p.print_help()


if __name__ == "__main__":
    main()
