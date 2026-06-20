# Pre-1870 White Heritage American Ancestry Model and Electoral College Reapportionment

This package estimates what share of each U.S. state's current population descends from White residents living in the United States before 1870, then asks: **what would the Electoral College look like if the census counted only that population?**

The model is a counterfactual apportionment exercise. It does not predict how anyone would vote.

## Key outputs

### Share of U.S. population with pre-1870 White Heritage American ancestry, 1870-2020

![National White Heritage American share over time](outputs/pct_white_heritage_over_time.png)

### U.S. population by White Heritage American ancestry status

![Raw headcount](outputs/raw_headcount_white_heritage.png)

### State-level White Heritage American ancestry share (agent-based model)

![State map](outputs/map_white_heritage_pct_by_state.png)

### Hypothetical Electoral College reapportionment

![EC cartogram](outputs/map_hypothetical_ec_2024_cartogram.png)

### Legal immigration to the United States by region of origin, 1820-2016

![Immigration by region, absolute](outputs/immigration_by_region_absolute.png)

![Immigration by region, share](outputs/immigration_by_region_share.png)

![Immigration by region, small multiples](outputs/immigration_by_region_small_multiples.png)

## Two state-level models

Both models define the qualifying ("White Heritage American") source stock as
residents enumerated as **White** in the 1870 Census — Black, American Indian /
Alaska Native, and other non-white (e.g. Chinese) 1870 residents are excluded from
the qualifying stock but remain in the present-day denominator.

The project implements two independent approaches to state-level estimation:

**Method A — Reduced-form model** (`state_pre1870_ancestry_model.py`): Uses ACS foreign-born and Black-alone shares with calibration to national anchors. Fast but relies on hand-set `old_stock_factor` priors per state, which also absorb residual non-white / non-old-stock population (it does not subtract AIAN/other races explicitly).

**Method B — Agent-based simulation** (`state_agent_ancestry_model.py`): Runs 300K agents through 1870-2020 using historical Census data from NHGIS (population, race, and nativity by state per decade). The 1870 qualifying stock is seeded from each state's enumerated **White** share (excluding Black, AIAN, and other races); state differences emerge from the simulation — no hand-set factors. This is the method behind the headline state map and EC cartogram.

The notebook runs both and compares results.

## Data sources

All model inputs are loaded from CSV files in `data/`, not hardcoded:

| File | Source | Content |
|------|--------|---------|
| `national_decade_data.csv` | Census POP-WP056, DHS Yearbook, Haines, NCHS | National population, foreign-born share, TFR, LPR admissions by decade |
| `national_1870_baseline.csv` | Census POP-WP056, NHGIS 1870_cPAX | 1870 total population, White population (qualifying stock), Black population, foreign-born share |
| `nhgis_historical_state_panel_1790_1990.csv` | IPUMS NHGIS API extracts | State-level total, White, Black, AIAN, foreign-born by decade |
| `modern_census_state_race_2000_2020.csv` | Census Bureau API (dec/sf1, dec/pl) | State-level total, Black, AIAN for 2000/2010/2020 |
| `dhs_lpr_by_decade.csv` | DHS/OHSS Yearbook Table 1 | Gross LPR admissions by decade, 1820-2010 |
| `fertility_by_nativity.csv` | Haines (Historical Statistics); Census ACS / CIS; Pew/NCHS | Foreign-born:native fertility ratio by decade |
| `dhs_lpr_by_country_decade.csv` | DHS/OHSS Yearbook 2016, Table 2 (pp. 6-11) | Verbatim country-level LPR admissions by decade, 1820-2016, tagged with each row's continent and assigned world region (the auditable raw extract) |
| `immigration_by_region_decade.csv` | Derived from `dhs_lpr_by_country_decade.csv` | LPR admissions aggregated to world region by decade; built and validated by `scripts/build_immigration_by_region.py` |
| `state_fips_2024_electoral_votes.csv` | National Archives | State FIPS codes and 2024 EV baseline |

## Project structure

```text
pre1870_reapportionment_package/
├── scripts/
│   ├── pre1870_ancestry_model.py          # National agent-based cohort simulation
│   ├── state_pre1870_ancestry_model.py    # State reduced-form model (Method A)
│   ├── state_agent_ancestry_model.py      # State agent-based model (Method B)
│   ├── hypothetical_ec_reapportionment.py # Electoral College reapportionment
│   ├── fetch_nhgis_state_panel.py         # NHGIS API data acquisition
│   ├── build_immigration_by_region.py     # Aggregate country-level DHS data to world regions (validated)
│   ├── plot_immigration_by_region.py      # Charts of immigration by region of origin, 1820-2016
│   ├── generate_figures.py               # Regenerate headline PNG figures (no API key)
│   └── ...
├── data/
│   ├── national_decade_data.csv           # National population anchors (with sources)
│   ├── national_1870_baseline.csv         # 1870 baseline values (with sources)
│   ├── nhgis_historical_state_panel_1790_1990.csv  # Historical state panel
│   ├── modern_census_state_race_2000_2020.csv      # Modern Census API data
│   ├── dhs_lpr_by_decade.csv              # Immigration admissions
│   └── geo/                               # Shapefiles for mapping
├── outputs/                               # Generated CSV and image outputs
├── notebooks/
│   └── old_stock_analysis.ipynb           # Main analysis notebook
├── fetch_pre1870_inputs.py                # Data acquisition: Census API, static inputs
├── MATH_AND_METHODS.md                    # Full mathematical specification
└── ASSUMPTIONS.md                         # Model assumptions and sensitivity
```

## Quick start

```bash
pip install -r requirements.txt
```

### 1. Fetch NHGIS historical data (requires NHGIS API key)

```bash
export NHGIS_API_KEY="your_nhgis_key"
python scripts/fetch_nhgis_state_panel.py
```

Or process an already-downloaded extract:

```bash
python scripts/fetch_nhgis_state_panel.py --from-zip nhgis_cache/nhgis_extract_2.zip nhgis_cache/nhgis_extract_3.zip
```

### 2. Fetch modern Census data (requires Census API key)

```bash
export CENSUS_API_KEY="your_census_key"
python fetch_pre1870_inputs.py --fetch-modern-census --write-static --validate
```

### 3. Run the national ancestry model

```bash
python scripts/pre1870_ancestry_model.py
python scripts/pre1870_ancestry_model.py --sensitivity
```

### 4. Run the state-level agent-based model

```bash
python scripts/state_agent_ancestry_model.py --n-agents 300000 --seeds 1870,1871,1872
```

### 5. Run the Electoral College reapportionment

```bash
python scripts/hypothetical_ec_reapportionment.py \
  --input outputs/state_agent_estimates.csv \
  --metric primary \
  --output-csv outputs/hypothetical_ec_reapportionment_primary.csv
```

### 6. Regenerate the headline figures

Regenerates the four README figures from the national model and the committed
agent estimates. No Census API key or notebook required:

```bash
python scripts/generate_figures.py
```

This writes `pct_white_heritage_over_time.png`, `raw_headcount_white_heritage.png`,
`map_white_heritage_pct_by_state.png`, and `map_hypothetical_ec_2024_cartogram.png`
to `outputs/`.

### 7. Run the full analysis notebook

```bash
export CENSUS_API_KEY="your_census_key"
jupyter notebook notebooks/old_stock_analysis.ipynb
```

### 8. Plot immigration by world region of origin

```bash
# (optional) rebuild the regional aggregates from the country-level extract
python scripts/build_immigration_by_region.py
# render the charts
python scripts/plot_immigration_by_region.py
```

Produces stacked-area, 100%-share, and small-multiples charts of legal
immigration by world region, 1820-2016, in `outputs/`.

**Provenance.** Every value traces to DHS/OHSS *Yearbook of Immigration
Statistics 2016*, Table 2 (*Persons Obtaining Lawful Permanent Resident Status by
Region and Selected Country of Last Residence: Fiscal Years 1820 to 2016*,
[PDF](https://ohss.dhs.gov/sites/default/files/2023-12/2016%2520Yearbook%2520of%2520Immigration%2520Statistics.pdf),
pp. 6-11). `dhs_lpr_by_country_decade.csv` is a verbatim transcription;
`build_immigration_by_region.py` aggregates it to regions and **asserts** that
the regions sum to the published grand total — and that the Europe/Asia/Africa
member countries reproduce the published continental subtotals — for every decade.

**Region definitions and source limitations (transparent choices).**

- Europe is split using the source's own country rows; "Other Europe"
  (post-1991 successor states, etc.) is assigned to Eastern Europe.
- The historical table itemizes only 13 Asian countries, so `South Asia` is
  **India only**, `Southeast Asia` is the **Philippines and Vietnam only**, and
  every other Asian origin (Pakistan, Bangladesh, Iraq, Indonesia, ...) falls in
  `Other Asia`. Legend labels state these contents explicitly.
- `Middle East & North Africa` combines West-Asian rows (Iran, Israel, Jordan,
  Syria, Turkey) with North-African rows (Egypt, Morocco), crossing the source's
  Asia/Africa boundary by design.
- `Other & not specified` = Oceania + Other America + Not Specified.
- `2010-16` is a partial decade (it sums fiscal years 2010-2016 only) and is
  flagged as such in the charts.

## Safe key handling

Do not commit API keys. Use environment variables:

```bash
export CENSUS_API_KEY="your_census_key"
export NHGIS_API_KEY="your_nhgis_key"
```

## NHGIS citation

This project uses NHGIS data. If you use these results, cite:

> Jonathan Schroeder, David Van Riper, Steven Manson, Katherine Knowles, Tracy Kugler, Finn Roberts, and Steven Ruggles. IPUMS National Historical Geographic Information System: Version 20.0 [dataset]. Minneapolis, MN: IPUMS. 2025. http://doi.org/10.18128/D050.V20.0

## Documentation

- **[MATH_AND_METHODS.md](MATH_AND_METHODS.md)** — Full mathematical specification
- **[ASSUMPTIONS.md](ASSUMPTIONS.md)** — Model assumptions and sensitivity parameters

## Dependencies

- Python 3.9+
- `numpy` — agent-based simulation
- `pandas` — data manipulation and reapportionment
- `requests` — Census and NHGIS API calls
- `matplotlib` — visualizations
- `plotly` — optional, interactive HTML map
