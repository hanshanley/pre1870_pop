# Pre-1870 Ancestry Stock Model and Electoral College Reapportionment

This package estimates what share of each U.S. state's current population descends from people living in the United States before 1870, then asks: **what would the Electoral College look like if the census counted only that population?**

The model is a counterfactual apportionment exercise. It does not predict how anyone would vote.

## Project structure

```text
pre1870_reapportionment_package/
├── fetch_pre1870_inputs.py              # Data acquisition: Census API, static inputs
├── scripts/
│   ├── pre1870_ancestry_model.py        # National agent-based cohort simulation
│   ├── state_pre1870_ancestry_model.py  # State-level reduced-form ancestry model
│   └── hypothetical_ec_reapportionment.py  # Electoral College reapportionment (Huntington-Hill)
├── data/
│   ├── dhs_lpr_by_decade.csv            # Gross LPR admissions by decade (DHS Yearbook Table 1)
│   ├── state_fips_2024_electoral_votes.csv  # FIPS codes, abbreviations, 2024 EV baseline
│   ├── source_manifest.csv              # Source checklist for all required datasets
│   ├── native_correction_notes.csv      # Notes on Native American under-enumeration
│   ├── modern_census_state_race_2000_2020.csv  # [generated] State-level Census API data
│   ├── modern_census_us_race_2000_2020.csv     # [generated] National Census API data
│   └── geo/                             # Shapefiles for mapping
├── outputs/
│   ├── state_pre1870_estimates.csv      # State-level ancestry share estimates
│   ├── state_pre1870_estimates_sensitivity.csv  # Sensitivity scenarios
│   ├── hypothetical_ec_reapportionment_primary.csv  # Reapportioned EV table
│   └── hypothetical_ec_reapportionment_primary_map.html  # Interactive choropleth
├── notebooks/
│   └── old_stock_analysis.ipynb         # Exploratory analysis notebook
├── census_cache/                        # Cached Census API responses (JSON)
├── MATH_AND_METHODS.md                  # Full mathematical specification
├── ASSUMPTIONS.md                       # Model assumptions and sensitivity parameters
├── PACKAGE_MANIFEST.csv                 # File inventory with sizes
├── requirements.txt                     # Python dependencies
└── .env.example                         # Template for Census API key
```

## Quick start

```bash
pip install -r requirements.txt
```

### 1. Write static inputs (no API key needed)

```bash
python fetch_pre1870_inputs.py --write-static --validate
```

### 2. Fetch modern Census data (requires API key)

```bash
export CENSUS_API_KEY="YOUR_CENSUS_KEY"
python fetch_pre1870_inputs.py --fetch-modern-census --validate
```

### 3. Run the national ancestry model

```bash
python scripts/pre1870_ancestry_model.py
python scripts/pre1870_ancestry_model.py --json              # JSON output
python scripts/pre1870_ancestry_model.py --sensitivity        # Run sensitivity grid
python scripts/pre1870_ancestry_model.py --include-black-1870 # Include 1870 Black pop as qualifying
```

### 4. Run the state-level model

```bash
# Using built-in fallback priors (no API key needed)
python scripts/state_pre1870_ancestry_model.py --use-fallback --output outputs/state_pre1870_estimates.csv

# Using live ACS data
python scripts/state_pre1870_ancestry_model.py --download-acs --output outputs/state_pre1870_estimates.csv

# With sensitivity analysis
python scripts/state_pre1870_ancestry_model.py --use-fallback --sensitivity --output outputs/state_pre1870_estimates.csv
```

### 5. Run the Electoral College reapportionment

```bash
python scripts/hypothetical_ec_reapportionment.py \
  --input outputs/state_pre1870_estimates.csv \
  --metric primary \
  --output-csv outputs/hypothetical_ec_reapportionment_primary.csv \
  --output-html outputs/hypothetical_ec_reapportionment_primary_map.html
```

Alternative metrics: `any`, `average`, `primary` (default).

## Safe key handling

Do not put your Census API key directly in the command line or commit it to a file. Use an environment variable:

```bash
export CENSUS_API_KEY="YOUR_CENSUS_KEY"
```

The script redacts the key from error messages and does not store the key in output CSVs. To print query templates without the key:

```bash
python fetch_pre1870_inputs.py --show-queries
```

## Historical data (requires manual setup)

The model benefits from historical state-level race/nativity data for 1790-1990. The best source is [IPUMS NHGIS](https://www.nhgis.org/).

Expected cleaned file:

```text
data/nhgis_historical_state_panel_1790_1990.csv
```

Required columns: `year`, `state`, `abbr`, `total`. Optional columns that improve accuracy: `black`, `aian`, `foreign_born`, `native_parentage`.

## Documentation

- **[MATH_AND_METHODS.md](MATH_AND_METHODS.md)** — Full mathematical specification: cohort model equations, Huntington-Hill apportionment, data inputs, validation checks, and limitations.
- **[ASSUMPTIONS.md](ASSUMPTIONS.md)** — Model assumptions, default parameters, sensitivity ranges, and data source bibliography.

## Dependencies

- Python 3.9+
- `requests` — for Census API calls
- `pandas` — for the reapportionment script
- `numpy` — for the national agent-based model
- `plotly` — optional, for the interactive HTML map
