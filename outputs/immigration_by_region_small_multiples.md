# U.S. immigration by region of origin — small multiples (per decade)

![Immigration by region, small multiples](immigration_by_region_small_multiples.png)

## What this figure shows

One panel per world region (14 panels), each plotting that region's **number of
immigrants per decade** from **1820 to 2016** on its own y-axis. Because each
panel is scaled independently, this view reveals the *timing and shape* of each
region's wave — even for regions too small to read in the stacked charts:

- **Northern & Western Europe** crests in the 1880s, then declines.
- **Southern** and **Eastern Europe** spike sharply around 1900–1910.
- **East Asia** shows an early-1900s bump, a mid-century gap, then a post-1965 rise.
- **South Asia (India)**, **Southeast Asia**, **Sub-Saharan Africa**,
  **Mexico & Central America**, **Caribbean**, and **South America** all climb
  mainly after 1965.
- **Canada** peaks in the 1880s and 1920s.

Unlike the two stacked charts, these panels are **not smoothed** — they show the
raw decade values directly (each point is a published decade figure).

## Data source

> U.S. Department of Homeland Security, Office of Homeland Security Statistics
> (OHSS). *2016 Yearbook of Immigration Statistics*, **Table 2 — Persons
> Obtaining Lawful Permanent Resident Status by Region and Selected Country of
> Last Residence: Fiscal Years 1820 to 2016** (pp. 6–11).

PDF: <https://ohss.dhs.gov/sites/default/files/2023-12/2016%2520Yearbook%2520of%2520Immigration%2520Statistics.pdf>
(linked from <https://ohss.dhs.gov/topics/immigration/yearbook/2023>).

Prior to 1906 the table reflects country of **origin**; from 1906, country of
**last residence** (source footnote 1).

## How it is made

```
data/dhs_lpr_by_country_decade.csv   →  scripts/build_immigration_by_region.py
   →  data/immigration_by_region_decade.csv  →  scripts/plot_immigration_by_region.py
   →  outputs/immigration_by_region_small_multiples.png
```

Regenerate:

```bash
python scripts/build_immigration_by_region.py
python scripts/plot_immigration_by_region.py
```

## Region definitions and source limitations

See [`immigration_by_region_absolute.md`](immigration_by_region_absolute.md) for
the full region-membership table. In brief:

- Europe split into **Northern & Western / Southern / Eastern**; "Other Europe"
  is assigned to Eastern Europe.
- **South Asia = India only**; **Southeast Asia = Philippines + Vietnam only**.
  The 1820–2016 table itemizes only 13 Asian countries, so other Asian origins —
  including **Indonesia**, Thailand, Pakistan, Bangladesh, Iraq, etc. — are
  collapsed by the source into **Other Asia** and cannot be separated.
- **Sub-Saharan Africa** = Africa excluding Egypt and Morocco.
- **Middle East & North Africa** = Iran, Israel, Jordan, Syria, Turkey + Egypt,
  Morocco.
- **Other & not specified** = Oceania + Other America + Not Specified.
- `2010–16` is a partial decade (fiscal years 2010–2016).

## Verification

The data behind every panel is validated at build time:
`scripts/build_immigration_by_region.py` asserts, for each decade, that the 14
regions sum to the published DHS grand total and that the Europe/Asia/Africa
member countries reproduce the published continental subtotals. Figures are
reproduced exactly as published; nothing is rounded, imputed, or invented here.
