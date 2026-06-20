#!/usr/bin/env python3
"""
fetch_nhgis_state_panel.py

Fetch historical state-level Census data from the IPUMS NHGIS API and produce
a harmonized panel CSV covering 1790-1990.

The output file, data/nhgis_historical_state_panel_1790_1990.csv, is consumed
by the state-level agent-based ancestry model.

Usage
-----
    # Submit extract, wait, download, and build panel
    export NHGIS_API_KEY="your_key"
    python scripts/fetch_nhgis_state_panel.py

    # Just process an already-downloaded extract zip
    python scripts/fetch_nhgis_state_panel.py --from-zip path/to/nhgis_csv.zip

Requires: Python 3.9+, requests.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import pathlib
import re
import sys
import time
import zipfile
from typing import Dict, List, Optional, Tuple

try:
    import requests
except ImportError as exc:
    raise SystemExit("Install requests first: pip install requests") from exc

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CACHE_DIR = ROOT / "cache"

NHGIS_API_KEY = os.environ.get("NHGIS_API_KEY", "")
API_BASE = "https://api.ipums.org"

# ── NHGIS extract specification ───────────────────────────────────────────
# Each entry: (dataset, [tables], decade_year)
# Tables are chosen to provide total population, race/slave-status, and
# nativity/foreign-born where available.

EXTRACT_SPEC = {
    "1790_cPop":   {"data_tables": ["NT1", "NT6"],       "geog_levels": ["state"]},
    "1800_cPop":   {"data_tables": ["NT1"],               "geog_levels": ["state"]},
    "1810_cPop":   {"data_tables": ["NT1"],               "geog_levels": ["state"]},
    "1820_cPop":   {"data_tables": ["NT1"],               "geog_levels": ["state"]},
    "1830_cPop":   {"data_tables": ["NT1", "NT13", "NT9"],"geog_levels": ["state"]},
    "1840_cPopX":  {"data_tables": ["NT1"],               "geog_levels": ["state"]},
    "1850_cPAX":   {"data_tables": ["NT1", "NT6", "NT40"],"geog_levels": ["state"]},
    "1860_cPAX":   {"data_tables": ["NT1", "NT6", "NT9A"],"geog_levels": ["state"]},
    "1870_cPAX":   {"data_tables": ["NT1", "NT4", "NT5"], "geog_levels": ["state"]},
    "1880_cPAX":   {"data_tables": ["NT1", "NT4", "NT52"],"geog_levels": ["state"]},
    "1890_cPHAM":  {"data_tables": ["NT1", "NT4", "NT5"], "geog_levels": ["state"]},
    "1900_cPHAM":  {"data_tables": ["NT1", "NT4", "NT7"], "geog_levels": ["state"]},
    "1910_cPHA":   {"data_tables": ["NT1", "NT8", "NT11"],"geog_levels": ["state"]},
    "1920_cPHAM":  {"data_tables": ["NT1", "NT5", "NT6"], "geog_levels": ["state"]},
    "1930_cPAE":   {"data_tables": ["NT1", "NT5", "NT7"], "geog_levels": ["state"]},
    "1940_cPHAE":  {"data_tables": ["NT1", "NT5", "NT6"], "geog_levels": ["state"]},
    "1950_cPHA":   {"data_tables": ["NT6", "NT9A"],       "geog_levels": ["state"]},
    "1960_cPop":   {"data_tables": ["NT1", "NT2", "NT13"],"geog_levels": ["state"]},
    "1970_Cnt4Pa": {"data_tables": ["NT105", "NT107"],    "geog_levels": ["state"]},
    "1980_STF1":   {"data_tables": ["NT9B"],              "geog_levels": ["state"]},
    "1980_STF4Pa": {"data_tables": ["NTPA93"],            "geog_levels": ["state"]},
    "1990_STF1":   {"data_tables": ["NP6"],               "geog_levels": ["state"]},
    "1990_STF3":   {"data_tables": ["NP42"],              "geog_levels": ["state"]},
}

# ── Historical state name → modern abbreviation mapping ──────────────────
# NHGIS uses historical names (including "Territory" suffixes). This maps
# them to modern two-letter abbreviations.

HISTORICAL_STATE_MAP: Dict[str, str] = {
    "Alabama": "AL", "Alaska": "AK", "Alaska Territory": "AK",
    "Arizona": "AZ", "Arizona Territory": "AZ",
    "Arkansas": "AR",
    "California": "CA",
    "Colorado": "CO", "Colorado Territory": "CO",
    "Connecticut": "CT",
    "Dakota Territory": None,  # split to ND+SD in post-processing
    "Delaware": "DE",
    "District Of Columbia": "DC", "District of Columbia": "DC",
    "Florida": "FL", "Florida Territory": "FL",
    "Georgia": "GA",
    "Hawaii": "HI", "Hawaii Territory": "HI",
    "Idaho": "ID", "Idaho Territory": "ID",
    "Illinois": "IL",
    "Indiana": "IN", "Indiana Territory": "IN",
    "Iowa": "IA", "Iowa Territory": "IA",
    "Kansas": "KS", "Kansas Territory": "KS",
    "Kentucky": "KY",
    "Louisiana": "LA", "Louisianna": "LA",
    "Maine": "ME",
    "Maryland": "MD",
    "Massachusetts": "MA",
    "Michigan": "MI", "Michigan Territory": "MI",
    "Minnesota": "MN", "Minnesota Territory": "MN",
    "Mississippi": "MS", "Mississippi Territory": "MS",
    "Missouri": "MO", "Missouri Territory": "MO",
    "Montana": "MT", "Montana Territory": "MT",
    "Nebraska": "NE", "Nebraska Territory": "NE",
    "Nevada": "NV",
    "New Hampshire": "NH",
    "New Jersey": "NJ",
    "New Mexico": "NM", "New Mexico Territory": "NM",
    "New York": "NY",
    "North Carolina": "NC",
    "North Dakota": "ND",
    "Ohio": "OH",
    "Oklahoma": "OK", "Oklahoma Territory": "OK", "Indian Territory": "OK",
    "Oregon": "OR", "Oregon Territory": "OR",
    "Pennsylvania": "PA",
    "Rhode Island": "RI",
    "South Carolina": "SC",
    "South Dakota": "SD",
    "Tennessee": "TN",
    "Texas": "TX",
    "Utah": "UT", "Utah Territory": "UT",
    "Vermont": "VT",
    "Virginia": "VA",
    "Washington": "WA", "Washington Territory": "WA",
    "West Virginia": "WV",
    "Wisconsin": "WI", "Wisconsin Territory": "WI",
    "Wyoming": "WY", "Wyoming Territory": "WY",
    # Pre-statehood combined territories
    "Orleans Territory": "LA",
    "Southwest Territory": "TN",
    "Northwest Territory": None,
}

MODERN_FIPS: Dict[str, str] = {
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

ABBR_TO_NAME: Dict[str, str] = {
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


# ── API helpers ───────────────────────────────────────────────────────────

def api_headers() -> Dict[str, str]:
    return {"Authorization": NHGIS_API_KEY, "Content-Type": "application/json"}


def _set_api_key(key: str) -> None:
    global NHGIS_API_KEY
    NHGIS_API_KEY = key


def submit_extract() -> int:
    payload = {
        "datasets": EXTRACT_SPEC,
        "data_format": "csv_no_header",
        "description": "Historical state panel 1790-1990: total pop, race, nativity",
    }
    r = requests.post(
        f"{API_BASE}/extracts?collection=nhgis&version=v1",
        headers=api_headers(), json=payload, timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    print(f"Submitted extract #{data['number']}, status: {data['status']}")
    return data["number"]


def wait_for_extract(extract_num: int, poll_seconds: int = 15, max_wait: int = 600) -> Dict:
    elapsed = 0
    while elapsed < max_wait:
        r = requests.get(
            f"{API_BASE}/extracts/{extract_num}?collection=nhgis&version=v1",
            headers=api_headers(), timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        status = data["status"]
        if status == "completed":
            print(f"Extract #{extract_num} completed.")
            return data
        if status == "failed":
            raise RuntimeError(f"Extract #{extract_num} failed: {data}")
        print(f"  Status: {status} ({elapsed}s elapsed)...")
        time.sleep(poll_seconds)
        elapsed += poll_seconds
    raise TimeoutError(f"Extract #{extract_num} not ready after {max_wait}s")


def download_extract(download_url: str, dest: pathlib.Path) -> pathlib.Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(download_url, headers=api_headers(), timeout=120, stream=True)
    r.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)
    print(f"Downloaded to {dest}")
    return dest


# ── CSV parsing and harmonization ─────────────────────────────────────────

def safe_int(val: str) -> Optional[int]:
    if not val or val.strip() == "":
        return None
    try:
        return int(float(val.strip()))
    except (ValueError, TypeError):
        return None


def resolve_abbr(state_name: str) -> Optional[str]:
    state_name = state_name.strip()
    if state_name in HISTORICAL_STATE_MAP:
        return HISTORICAL_STATE_MAP[state_name]
    for key in HISTORICAL_STATE_MAP:
        if key.lower() == state_name.lower():
            return HISTORICAL_STATE_MAP[key]
    return None


def parse_nhgis_zip(zip_path: pathlib.Path) -> Dict[Tuple[int, str], Dict]:
    """Parse all CSV files in an NHGIS extract zip.

    Returns {(year, abbr): {col_code: value, ...}} with raw NHGIS column codes.
    """
    records: Dict[Tuple[int, str], Dict] = {}
    # Collect records that map to None (e.g., Dakota Territory) for post-processing
    unresolved: List[Tuple[int, str, Dict]] = []

    with zipfile.ZipFile(zip_path) as zf:
        csv_files = [n for n in zf.namelist() if n.endswith(".csv")]
        for csv_name in csv_files:
            with zf.open(csv_name) as f:
                reader = csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig"))
                for row in reader:
                    year = int(row["YEAR"])
                    state_name = row.get("STATE") or row.get("AREANAME", "")
                    abbr = resolve_abbr(state_name)
                    if abbr is None:
                        if "Dakota" in state_name:
                            data = {col: val for col, val in row.items()
                                    if col not in ("GISJOIN", "YEAR", "STATE", "STATEA",
                                                   "COUNTYA", "AREANAME", "STATEICP", "COUNTYICP")}
                            unresolved.append((year, state_name, data))
                        continue
                    key = (year, abbr)
                    if key not in records:
                        records[key] = {}
                    for col, val in row.items():
                        if col not in ("GISJOIN", "YEAR", "STATE", "STATEA",
                                       "COUNTYA", "AREANAME", "STATEICP", "COUNTYICP"):
                            records[key][col] = val

    # Split Dakota Territory 50/50 into ND and SD for pre-1890 decades
    for year, name, data in unresolved:
        for abbr in ("ND", "SD"):
            key = (year, abbr)
            if key not in records:
                records[key] = {}
            for col, val in data.items():
                try:
                    numeric = int(float(val))
                    records[key][col] = str(numeric // 2)
                except (ValueError, TypeError):
                    records[key][col] = val

    return records


def _g(cols: Dict[str, Optional[int]], key: str) -> Optional[int]:
    return cols.get(key)


def _sum(cols: Dict[str, Optional[int]], *keys: str) -> Optional[int]:
    vals = [cols[k] for k in keys if k in cols and cols[k] is not None]
    return sum(vals) if vals else None


def harmonize_records(records: Dict[Tuple[int, str], Dict]) -> List[Dict]:
    """Convert raw NHGIS column-coded records into the harmonized schema.

    Uses explicit column-code mappings derived from NHGIS codebooks for this
    specific extract. Each decade maps known NHGIS variable codes to our
    output schema: total, black, aian, foreign_born.
    """
    rows = []
    for (year, abbr), cols in sorted(records.items()):
        col_vals = {k: safe_int(v) for k, v in cols.items()}
        total, white, black, aian, foreign_born, native_parentage = _extract_fields(year, col_vals)

        if total is not None and total > 0:
            rows.append({
                "year": year,
                "state": ABBR_TO_NAME.get(abbr, abbr),
                "abbr": abbr,
                "fips": MODERN_FIPS.get(abbr, ""),
                "total": total,
                "white": white,
                "black": black,
                "aian": aian,
                "foreign_born": foreign_born,
                "native_parentage": native_parentage,
            })

    return sorted(rows, key=lambda r: (r["year"], r["abbr"]))


def _extract_fields(year: int, c: Dict[str, Optional[int]]) -> Tuple[
    Optional[int], Optional[int], Optional[int], Optional[int], Optional[int], Optional[int]
]:
    """Extract total, white, black, aian, foreign_born, native_parentage from NHGIS columns.

    Column codes are specific to this extract and were verified against codebooks.
    The enumerated White count is captured so downstream models can define the
    "White Heritage" source stock directly (excluding Black, AIAN, and other
    non-white races) rather than approximating it as total minus Black.
    """
    total = None
    white = None
    black = None
    aian = None
    foreign_born = None
    native_parentage = None

    if year == 1790:
        # AAA001: Total | AAQ001: Non-White Free | AAQ002: Non-White Slave | AAQ003: White
        total = _g(c, "AAA001")
        white = _g(c, "AAQ003")
        black = _sum(c, "AAQ001", "AAQ002")  # free + slave = total non-white (mostly Black)

    elif year == 1800:
        # AAS001: Total
        total = _g(c, "AAS001")

    elif year == 1810:
        # AA1001: Total
        total = _g(c, "AA1001")

    elif year == 1820:
        # ABA001: Total
        total = _g(c, "ABA001")

    elif year == 1830:
        # ABN001: Total (from NT1) | AB1001: Total (from NT9 — foreigners not naturalized)
        # ABP001: White | ABP002: Non-white
        total = _g(c, "ABN001")
        white = _g(c, "ABP001")
        black = _g(c, "ABP002")
        foreign_born = _g(c, "AB1001")

    elif year == 1840:
        # ACD001: Total
        total = _g(c, "ACD001")

    elif year == 1850:
        # ADQ001: Total | AE6001: White | AE6002: Nonwhite Free | AE6003: Nonwhite Slave
        # AEM001: Born out of state | AEM002: Born out of country
        total = _g(c, "ADQ001")
        white = _g(c, "AE6001")
        black = _sum(c, "AE6002", "AE6003")
        foreign_born = _g(c, "AEM002")

    elif year == 1860:
        # AG3001: Total | AH3001: White | AH3002: Free colored | AH3003: Slave
        # AH3004: Indian | AH3005: Half breed | AH3006: Asiatic
        # AH6001: Native-born | AH6002: Foreign-born
        total = _g(c, "AG3001")
        white = _g(c, "AH3001")
        black = _sum(c, "AH3002", "AH3003")
        aian = _sum(c, "AH3004", "AH3005")
        foreign_born = _g(c, "AH6002")

    elif year == 1870:
        # AJ3001: Total | AK3001: White | AK3002: Colored | AK3003: Chinese | AK3004: Indian
        # ALB001: Native-born | ALB002: Foreign-born
        total = _g(c, "AJ3001")
        white = _g(c, "AK3001")
        black = _g(c, "AK3002")
        aian = _g(c, "AK3004")
        foreign_born = _g(c, "ALB002")

    elif year == 1880:
        # AOT001: Total | APP001: White | APP002: Colored | APP003: Chinese | APP004: Indian
        # AP4001: Native-born | AP4002: Foreign-born
        total = _g(c, "AOT001")
        white = _g(c, "APP001")
        black = _g(c, "APP002")
        aian = _g(c, "APP004")
        foreign_born = _g(c, "AP4002")

    elif year == 1890:
        # AUM001: Total
        # AVF001: Negro 1890 | AVF004: Chinese 1890 | AVF007: Japanese 1890 | AVF010: Civ Indian 1890
        # AVP001: Native Male | AVP002: Native Female | AVP003: FB Male | AVP004: FB Female
        total = _g(c, "AUM001")
        black = _g(c, "AVF001")
        aian = _g(c, "AVF010")
        foreign_born = _sum(c, "AVP003", "AVP004")
        # No reliable direct White code in this extract; leave white unset rather
        # than derive it from an uncertain race breakdown.

    elif year == 1900:
        # AYM001: Total
        # AZF001-4: Nativity by Sex (native M, native F, FB M, FB F)
        # AZ3001: Other Colored Male | AZ3002: Other Colored Female
        # AZ3003: Negro Male | AZ3004: Negro Female
        total = _g(c, "AYM001")
        black = _sum(c, "AZ3003", "AZ3004")
        foreign_born = _sum(c, "AZF003", "AZF004")
        # No reliable direct White code in this extract; leave white unset rather
        # than derive it from an uncertain race breakdown.

    elif year == 1910:
        # A3Y001: Total (1910) | A3Y002: Total (1900)
        # A5B001: Native-born native parentage | A5B002: Native-born foreign parentage
        # A5B003: Native-born mixed parentage | A5B004: Foreign-born
        # A30001: White Male | A30002: White Female | A30003: Negro Male | A30004: Negro Female
        total = _g(c, "A3Y001")
        white = _sum(c, "A30001", "A30002")
        black = _sum(c, "A30003", "A30004")
        foreign_born = _g(c, "A5B004")
        native_parentage = _g(c, "A5B001")

    elif year == 1920:
        # A7L001: Total
        # A8L001-4: White native M, White native F, White FB M, White FB F
        # A8L005: Negro Male | A8L006: Negro Female
        # A8V001: Native parentage | A8V002: Foreign parentage | A8V003: Mixed parentage
        total = _g(c, "A7L001")
        white = _sum(c, "A8L001", "A8L002", "A8L003", "A8L004")
        black = _sum(c, "A8L005", "A8L006")
        foreign_born = _sum(c, "A8L003", "A8L004")
        native_parentage = _g(c, "A8V001")

    elif year == 1930:
        # BDP001: Total
        # BEP001-4: White native M, White native F, White FB M, White FB F
        # BEP005: Negro Male | BEP006: Negro Female
        # BE8001: Native parentage | BE8002: Foreign parentage | BE8003: Mixed
        total = _g(c, "BDP001")
        white = _sum(c, "BEP001", "BEP002", "BEP003", "BEP004")
        black = _sum(c, "BEP005", "BEP006")
        foreign_born = _sum(c, "BEP003", "BEP004")
        native_parentage = _g(c, "BE8001")

    elif year == 1940:
        # BV7001: Total
        # BXY001-4: Native M, Native F, FB M, FB F
        # BYA001: White native | BYA002: White FB | BYA003: Negro | BYA004: Other
        total = _g(c, "BV7001")
        white = _sum(c, "BYA001", "BYA002")
        black = _g(c, "BYA003")
        foreign_born = _sum(c, "BXY003", "BXY004")

    elif year == 1950:
        # B3P001-8: Sex by Race/Nativity
        #   M White Native, M White FB, M Negro, M Other, F White Native, F White FB, F Negro, F Other
        # B4J001: Native-born | B4J002: Foreign-born
        total = _sum(c, "B3P001", "B3P002", "B3P003", "B3P004",
                        "B3P005", "B3P006", "B3P007", "B3P008")
        white = _sum(c, "B3P001", "B3P002", "B3P005", "B3P006")
        black = _sum(c, "B3P003", "B3P007")
        foreign_born = _g(c, "B4J002")

    elif year == 1960:
        # B5O001: Total Pop | B5V001: Foreign Stock (FB + native of foreign parentage — NOT just FB)
        # B5S001-14: Sex by Race (M White, M Negro, M Indian, M Japanese, M Chinese,
        #            M Filipino, M Other, F White, F Negro, F Indian, ...)
        total = _g(c, "B5O001")
        white = _sum(c, "B5S001", "B5S008")
        black = _sum(c, "B5S002", "B5S009")
        aian = _sum(c, "B5S003", "B5S010")
        # B5V001 is foreign stock, not foreign-born. No pure FB table in this extract.

    elif year == 1970:
        # Prefer 100% count data (1970_Cnt2 NT1: Sex by Race, 18 vars)
        # CEB001-009: Male by race, CEB010-018: Female by race
        total_100 = _sum(c, "CEB001", "CEB002", "CEB003", "CEB004", "CEB005",
                            "CEB006", "CEB007", "CEB008", "CEB009",
                            "CEB010", "CEB011", "CEB012", "CEB013", "CEB014",
                            "CEB015", "CEB016", "CEB017", "CEB018")
        if total_100:
            total = total_100
            white = _sum(c, "CEB001", "CEB010")
            black = _sum(c, "CEB002", "CEB011")
            aian = _sum(c, "CEB003", "CEB012")
        else:
            # Fallback to sample-based (1970_Cnt4Pa)
            # C0X001: White | C0X002: Negro | C0X003: Other
            total = _sum(c, "C0X001", "C0X002", "C0X003")
            white = _g(c, "C0X001")
            black = _g(c, "C0X002")
        # C0Z001: Native-born | C0Z002: Foreign-born (from sample data)
        foreign_born = _g(c, "C0Z002")

    elif year == 1980:
        # Prefer 100% PL94-171 race data
        # C6X001: White | C6X002: Black | C6X003: AIAN | C6X004: Asian/PI | C6X005: Other
        total_pl = _sum(c, "C6X001", "C6X002", "C6X003", "C6X004", "C6X005")
        if total_pl:
            total = total_pl
            white = _g(c, "C6X001")
            black = _g(c, "C6X002")
            aian = _g(c, "C6X003")
        else:
            # Fallback to STF1 NT9B
            # C9G001: White | C9G002: Black | C9G003: Amer Indian | C9G004: Other
            total_race = _sum(c, "C9G001", "C9G002", "C9G003", "C9G004")
            if total_race:
                total = total_race
            white = _g(c, "C9G001")
            black = _g(c, "C9G002")
            aian = _g(c, "C9G003")
        # From STF4Pa (ds110): DV0001-3: Nativity/Citizenship
        foreign_born = _sum(c, "DV0002", "DV0003")

    elif year == 1990:
        # From STF1 (ds120): EUY001-5: Race
        #   EUY001: White | EUY002: Black | EUY003: Amer Indian | EUY004: Asian/PI | EUY005: Other
        # From STF3 (ds123): E3N001-9: Place of Birth
        #   E3N001-5: Born in state/other US areas
        #   E3N006-9: Born abroad (various categories)
        total_race = _sum(c, "EUY001", "EUY002", "EUY003", "EUY004", "EUY005")
        if total_race:
            total = total_race
        white = _g(c, "EUY001")
        black = _g(c, "EUY002")
        aian = _g(c, "EUY003")
        foreign_born = _sum(c, "E3N006", "E3N007", "E3N008", "E3N009")

    return total, white, black, aian, foreign_born, native_parentage


def write_panel_csv(rows: List[Dict], path: pathlib.Path) -> None:
    fields = ["year", "state", "abbr", "fips", "total", "white", "black", "aian",
              "foreign_born", "native_parentage"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow(row)
    print(f"Wrote {len(rows)} rows to {path}")


def validate_panel(rows: List[Dict]) -> None:
    years = sorted(set(r["year"] for r in rows))
    print(f"\nYears present: {years}")
    print(f"Total rows: {len(rows)}")

    # Spot-check 1870
    for r in rows:
        if r["year"] == 1870 and r["abbr"] == "NY":
            print(f"\n1870 NY check: total={r['total']} (expected ~4,382,759)")
        if r["year"] == 1870 and r["abbr"] == "PA":
            print(f"1870 PA check: total={r['total']} (expected ~3,521,951)")

    for y in [1870, 1900, 1950]:
        yr_rows = [r for r in rows if r["year"] == y]
        tot = sum(r["total"] for r in yr_rows if r["total"])
        n_states = len(yr_rows)
        has_black = sum(1 for r in yr_rows if r.get("black") is not None)
        has_fb = sum(1 for r in yr_rows if r.get("foreign_born") is not None)
        has_white = sum(1 for r in yr_rows if r.get("white") is not None)
        white_tot = sum(r["white"] for r in yr_rows if r.get("white"))
        print(f"  {y}: {n_states} states, total_pop={tot:,}, "
              f"has_white={has_white}, white_pop={white_tot:,}, "
              f"has_black={has_black}, has_foreign_born={has_fb}")

    # Race subtotals must never exceed the total population.
    for r in rows:
        for part in ("white", "black", "aian"):
            v = r.get(part)
            if v is not None and r["total"] and v > r["total"]:
                print(f"  WARNING: {r['year']} {r['abbr']} {part}={v} exceeds total={r['total']}")


# ── CLI ───────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch NHGIS historical state panel and build harmonized CSV."
    )
    parser.add_argument("--from-zip", type=pathlib.Path, nargs="+",
                        help="Process already-downloaded NHGIS extract zip(s).")
    parser.add_argument("--extract-num", type=int,
                        help="Poll and download a previously submitted extract by number.")
    parser.add_argument("--api-key", default=NHGIS_API_KEY,
                        help="NHGIS API key (or set NHGIS_API_KEY env var).")
    parser.add_argument("--output", type=pathlib.Path,
                        default=DATA_DIR / "nhgis_historical_state_panel_1790_1990.csv",
                        help="Output CSV path.")
    args = parser.parse_args()

    _set_api_key(args.api_key)

    if args.from_zip:
        zip_paths = args.from_zip
    else:
        if not NHGIS_API_KEY:
            print("Set NHGIS_API_KEY or pass --api-key.", file=sys.stderr)
            return 1

        if args.extract_num:
            extract_num = args.extract_num
        else:
            extract_num = submit_extract()

        data = wait_for_extract(extract_num)
        dl_url = data["download_links"].get("table_data")
        if not dl_url:
            print("No download link found.", file=sys.stderr)
            return 1

        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        zip_paths = [CACHE_DIR / f"nhgis_extract_{extract_num}.zip"]
        download_extract(dl_url, zip_paths[0])

    print(f"\nParsing {len(zip_paths)} zip file(s)...")
    records: Dict[Tuple[int, str], Dict] = {}
    for zp in zip_paths:
        partial = parse_nhgis_zip(zp)
        for key, cols in partial.items():
            if key not in records:
                records[key] = {}
            records[key].update(cols)
    print(f"Parsed {len(records)} state-year records from NHGIS CSV files.")

    rows = harmonize_records(records)
    validate_panel(rows)
    write_panel_csv(rows, args.output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
