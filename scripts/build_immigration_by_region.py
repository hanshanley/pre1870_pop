#!/usr/bin/env python3
"""
build_immigration_by_region.py

Aggregate the auditable country-level immigration extract into world regions.

Inputs
------
data/dhs_lpr_by_country_decade.csv
    Verbatim transcription of DHS/OHSS Yearbook of Immigration Statistics 2016,
    Table 2 (Persons Obtaining Lawful Permanent Resident Status by Region and
    Selected Country of Last Residence: Fiscal Years 1820 to 2016), pp. 6-11.
    Each row carries:
      - row_type        : grand_total | continent | subregion | country | unspecified
      - dhs_continent   : the source's continental grouping
      - analytical_region: the world region this row is assigned to (blank if the
                           row is NOT part of the aggregation partition, e.g. a
                           country already counted inside a subregion total).

    The set of rows with a non-blank analytical_region forms an exact partition
    of the grand total: every immigrant is counted in exactly one region. This is
    asserted at build time (sum over regions == published "Total" row, per decade).

Output
------
data/immigration_by_region_decade.csv
    Tidy decade x region admissions used by scripts/plot_immigration_by_region.py.

Region assignment notes (transparent, documented choices)
---------------------------------------------------------
* Europe is split into Northern & Western / Southern / Eastern using the source's
  own country rows. "Other Europe" (post-1991 successor states, etc.) is assigned
  to Eastern Europe.
* The 2016 historical table itemizes only 13 Asian countries, so:
    - "South Asia"     contains only India (the sole itemized South Asian country);
    - "Southeast Asia" contains only the Philippines and Vietnam;
    - all other Asian origins (Pakistan, Bangladesh, Iraq, Indonesia, ...) fall in
      "Other Asia". These limitations are inherent to the source.
* "Middle East & North Africa" combines West-Asian rows (Iran, Israel, Jordan,
  Syria, Turkey) with North-African rows (Egypt, Morocco); it therefore crosses
  the source's Asia/Africa continental boundary by design.
* "Other & not specified" = Oceania + Other America + Not Specified.
* 2010-16 is a partial decade: it sums fiscal years 2010 through 2016 only.
"""

import os

import pandas as pd

DECADE_COLS = [
    "1820", "1830", "1840", "1850", "1860", "1870", "1880", "1890", "1900",
    "1910", "1920", "1930", "1940", "1950", "1960", "1970", "1980", "1990",
    "2000",
]
PARTIAL_YEARS = ["2010", "2011", "2012", "2013", "2014", "2015", "2016"]

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
    "Canada",
    "Other & not specified",
]


def decade_label(start):
    return "2010\u201316" if start == 2010 else f"{start}\u2013{start + 9}"


def build(country_csv, out_csv):
    df = pd.read_csv(country_csv)
    value_cols = DECADE_COLS + PARTIAL_YEARS
    for c in value_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)

    leaves = df[df["analytical_region"].notna() & (df["analytical_region"] != "")].copy()
    total_row = df[df["row_type"] == "grand_total"].iloc[0]

    # ---- Invariant 1: leaves partition the grand total exactly, every decade ----
    for c in value_cols:
        s = int(leaves[c].sum())
        t = int(total_row[c])
        assert s == t, f"partition mismatch in {c}: regions sum {s} != Total {t}"

    # ---- Invariant 2: leaves assigned to a DHS continent reproduce its subtotal ----
    for cont in ["Europe", "Asia", "Africa"]:
        sub = df[(df["row_type"] == "continent") & (df["dhs_continent"] == cont)]
        if sub.empty:
            continue
        members = leaves[leaves["dhs_continent"] == cont]
        for c in value_cols:
            assert int(members[c].sum()) == int(sub.iloc[0][c]), (
                f"{cont} subtotal mismatch in {c}"
            )

    # ---- Aggregate to region x decade ----
    rows = []
    grouped = leaves.groupby("analytical_region")
    for start in [int(c) for c in DECADE_COLS] + [2010]:
        if start == 2010:
            vals = grouped[PARTIAL_YEARS].sum().sum(axis=1)
            note = "Partial decade: sums fiscal years 2010\u20132016 only."
        else:
            vals = grouped[str(start)].sum()
            note = (
                "Persons obtaining LPR status by region of last residence "
                "(country of origin before 1906)."
            )
        for region in REGION_ORDER:
            rows.append(
                {
                    "decade_start": start,
                    "decade_label": decade_label(start),
                    "region": region,
                    "immigrants": int(vals.get(region, 0)),
                    "source": "DHS/OHSS Yearbook of Immigration Statistics 2016, Table 2",
                    "source_url": df["source_url"].iloc[0],
                    "notes": note,
                }
            )

    out = pd.DataFrame(rows)
    out.to_csv(out_csv, index=False)
    print(f"validation passed; wrote {out_csv} ({len(out)} rows)")


def main():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data = os.path.join(here, "data")
    build(
        os.path.join(data, "dhs_lpr_by_country_decade.csv"),
        os.path.join(data, "immigration_by_region_decade.csv"),
    )


if __name__ == "__main__":
    main()
