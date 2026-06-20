# Legal immigration to the United States by region of origin — absolute (per decade)

![Immigration by region, absolute](immigration_by_region_absolute.png)

## What this figure shows

A stacked-area chart of the **number of immigrants** (persons obtaining lawful
permanent resident status) admitted to the United States each decade from
**1820 to 2016**, split into 14 world regions of origin. It makes the classic
"waves" of U.S. immigration visible:

- 1820s–1880s: dominated by **Northern & Western Europe** (and Canada).
- 1890s–1920s: the surge from **Southern** and **Eastern Europe**.
- 1930s–1940s: a sharp contraction (1924 national-origins quotas, the Great
  Depression, and World War II).
- post-1965: the shift toward **Latin America, Asia, and Africa** after the 1965
  Immigration and Nationality Act ended the quota system.

The y-axis is millions of admissions per decade. `2010–16` is a **partial
decade** (it sums fiscal years 2010–2016 only) and is flagged in red on the axis.

## Data source

Every value traces to:

> U.S. Department of Homeland Security, Office of Homeland Security Statistics
> (OHSS). *2016 Yearbook of Immigration Statistics*, **Table 2 — Persons
> Obtaining Lawful Permanent Resident Status by Region and Selected Country of
> Last Residence: Fiscal Years 1820 to 2016** (pp. 6–11).

PDF: <https://ohss.dhs.gov/sites/default/files/2023-12/2016%2520Yearbook%2520of%2520Immigration%2520Statistics.pdf>
(linked from the OHSS Yearbook page <https://ohss.dhs.gov/topics/immigration/yearbook/2023>).

Note: prior to 1906 the table reflects country of **origin**; from 1906 it
reflects country of **last residence** (source footnote 1). Some countries are
also combined for certain periods because of changing borders — e.g., Poland is
included in Austria, Germany, Hungary, and Russia for 1899–1919, and Finland in
Russia for the same years (source footnotes 3 and 6). Figures are reproduced
exactly as published; no values are rounded, imputed, or invented here.

## How it is made

```
data/dhs_lpr_by_country_decade.csv        # verbatim transcription of DHS Table 2
        │                                  #   (each row tagged with continent + region)
        ▼  scripts/build_immigration_by_region.py   (aggregates + validates)
data/immigration_by_region_decade.csv     # tidy region × decade admissions
        │
        ▼  scripts/plot_immigration_by_region.py
outputs/immigration_by_region_absolute.png
```

Regenerate:

```bash
python scripts/build_immigration_by_region.py   # optional: rebuild + revalidate the CSV
python scripts/plot_immigration_by_region.py     # render the PNGs
```

**Smoothing.** Bands are interpolated between decade points with a
shape-preserving monotone cubic (`scipy.interpolate.PchipInterpolator`), which
never overshoots or dips below zero, so the curve passes through the actual
decade values without inventing peaks.

## Region definitions and source limitations

The 14 regions are an exact partition of DHS Table 2: every source row is
assigned to exactly one region (see the `analytical_region` column of
`data/dhs_lpr_by_country_decade.csv`). The full membership is:

| Region | Source rows it contains |
|--------|-------------------------|
| Northern & Western Europe | Belgium, Denmark, Finland, France, Germany, Ireland, Netherlands, Norway-Sweden, Switzerland, United Kingdom |
| Southern Europe | Greece, Italy, Portugal, Spain |
| Eastern Europe | Austria-Hungary, Bulgaria, Czechoslovakia, Poland, Romania, Russia, Yugoslavia, Other Europe |
| East Asia | China, Hong Kong, Japan, Korea, Taiwan |
| South Asia | India |
| Southeast Asia | Philippines, Vietnam |
| Other Asia | Other Asia (source aggregate) |
| Middle East & North Africa | Iran, Israel, Jordan, Syria, Turkey, Egypt, Morocco |
| Sub-Saharan Africa | Ethiopia, Liberia, South Africa, Other Africa |
| Mexico & Central America | Mexico, Central America |
| Caribbean | Caribbean |
| South America | South America |
| Canada | Canada and Newfoundland |
| Other & not specified | Oceania, Other America, Not Specified |

Key limitations, all inherited from the source (nothing is invented to fill gaps):

- **Why isn't Indonesia in "Southeast Asia"?** Because the 1820–2016 historical
  table itemizes only **13 Asian countries** (China, Hong Kong, India, Iran,
  Israel, Japan, Jordan, Korea, Philippines, Syria, Taiwan, Turkey, Vietnam).
  Every other Asian origin — Indonesia, Thailand, Pakistan, Bangladesh, Iraq,
  Saudi Arabia, etc. — is collapsed by DHS into a single **"Other Asia"** row and
  cannot be separated. So `South Asia` is **India only** and `Southeast Asia` is
  **the Philippines and Vietnam only**; everything else Asian sits in `Other
  Asia`. The legend and chart caption say this explicitly.
- **Sub-Saharan Africa** is defined as *Africa minus Egypt and Morocco* (the only
  itemized African countries besides Ethiopia, Liberia, and South Africa). The
  source's "Other Africa" aggregate may therefore include small numbers from
  other North African countries (e.g. Algeria, Tunisia, Libya, Sudan).
- Europe is split using the source's own country rows; "Other Europe" (post-1991
  successor states, etc.) is assigned to **Eastern Europe**.
- **Middle East & North Africa** combines West-Asian rows (Iran, Israel, Jordan,
  Syria, Turkey) with North-African rows (Egypt, Morocco), crossing the source's
  Asia/Africa boundary by design.
- **Other & not specified** = Oceania + Other America + Not Specified.

## Verification

`scripts/build_immigration_by_region.py` asserts, for **every decade**:

1. the region values **sum to the published grand total** (exact partition — no
   double counting, no omissions); and
2. the Europe / Asia / Africa member countries **reproduce the published
   continental subtotals** exactly.

The build fails loudly if either invariant is violated.
