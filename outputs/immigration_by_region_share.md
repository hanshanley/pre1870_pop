# Composition of U.S. immigration by region of origin — share (per decade)

![Immigration by region, share](immigration_by_region_share.png)

## What this figure shows

The same data as `immigration_by_region_absolute.png`, but **normalized to 100%**
within each decade. Instead of how *many* immigrants arrived, it shows what
*share* of each decade's immigrants came from each of the 14 world regions —
making the compositional shifts easy to read even across decades with very
different total volumes.

Reading it: the deep-blue **Northern & Western Europe** band fills most of the
chart through the 1880s, is displaced by **Southern/Eastern Europe** around
1900, and gives way after 1965 to **Latin America, Asia, and Africa**.

## Data source

> U.S. Department of Homeland Security, Office of Homeland Security Statistics
> (OHSS). *2016 Yearbook of Immigration Statistics*, **Table 2 — Persons
> Obtaining Lawful Permanent Resident Status by Region and Selected Country of
> Last Residence: Fiscal Years 1820 to 2016** (pp. 6–11).

PDF: <https://ohss.dhs.gov/sites/default/files/2023-12/2016%2520Yearbook%2520of%2520Immigration%2520Statistics.pdf>
(linked from <https://ohss.dhs.gov/topics/immigration/yearbook/2023>).

Prior to 1906 the table reflects country of **origin**; from 1906, country of
**last residence**.

## How it is made

```
data/dhs_lpr_by_country_decade.csv   →  scripts/build_immigration_by_region.py
   →  data/immigration_by_region_decade.csv  →  scripts/plot_immigration_by_region.py
   →  outputs/immigration_by_region_share.png
```

Regenerate:

```bash
python scripts/build_immigration_by_region.py
python scripts/plot_immigration_by_region.py
```

**Smoothing + normalization.** The absolute admissions are first smoothed with a
shape-preserving monotone cubic (`scipy.interpolate.PchipInterpolator`), then at
every interpolated x-position each region's value is divided by the sum across
regions. This guarantees the bands fill exactly to 100% everywhere while keeping
the curves smooth and faithful to the decade data points.

## Region definitions and source limitations

Identical to the absolute chart — see
[`immigration_by_region_absolute.md`](immigration_by_region_absolute.md) for the
full region-membership table. In brief:

- Europe split into Northern & Western / Southern / Eastern (with "Other Europe"
  assigned to Eastern Europe).
- **South Asia = India only**; **Southeast Asia = Philippines + Vietnam only**.
  The 1820–2016 table itemizes only 13 Asian countries, so other Asian origins —
  including **Indonesia**, Thailand, Pakistan, Bangladesh, Iraq, etc. — are
  collapsed by the source into **Other Asia** and cannot be separated.
- **Sub-Saharan Africa** = Africa excluding Egypt and Morocco (the source's
  "Other Africa" aggregate may include a few other North African countries).
- **Middle East & North Africa** = Iran, Israel, Jordan, Syria, Turkey + Egypt,
  Morocco.
- **Other & not specified** = Oceania + Other America + Not Specified.

`2010–16` is a partial decade (fiscal years 2010–2016); shares are still valid
because they are ratios within that period.

## Verification

The underlying `data/immigration_by_region_decade.csv` is validated at build time
to (1) sum to the published DHS grand total per decade and (2) reproduce the
published Europe/Asia/Africa continental subtotals. Because shares are computed
from those validated totals, each decade's bands sum to 100% by construction.
