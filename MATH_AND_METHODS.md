# Pre-1870 U.S. Ancestry Stock and Electoral College Reapportionment Model

## 1. Purpose

This project estimates a counterfactual:

> What would the Electoral College allocation look like if the census counted only people descended from U.S. residents who were already in the United States by roughly 1870?

The model is **not** a party-vote forecast. It does not estimate how anyone would vote. It is an apportionment exercise: construct a hypothetical counted population by state, reapportion the 435 House seats using the standard equal-proportions method, and then compute electoral votes as House seats plus two Senate electors per state.

The project has two layers:

1. **Ancestry-stock layer:** estimate the population in each state that belongs to the pre-1870 ancestry stock.
2. **Electoral College layer:** use the modeled counted population as the apportionment population.

The current package contains the data acquisition layer, static inputs, existing state-estimate outputs, and the Electoral College reapportionment script.

---

## 2. Key definitions

### 2.1 Pre-1870 stock

Let $S_{s,t}$ denote the modeled population in state $s$ at time $t$ whose ancestry descends from people resident in the United States before the 1870 cutoff.

In the updated definition requested here, the pre-1870 stock includes:

$$
\text{pre-1870 resident stock}
=
\text{White/European-origin resident stock}
+
\text{Black resident stock}
+
\text{Native American / Alaska Native resident stock}
+
\text{other resident stock present by the cutoff}
$$

It excludes:

$$
\text{post-1870 immigrant-entry cohorts and their descendants}
$$

This is a modeling definition, not a directly measured Census category.

### 2.2 Cutoff

The implementation uses decade cohorts. A practical cutoff is:

$$
c \leq 1860
$$

for cohorts entering before 1870. Depending on how one treats arrivals in the 1860s and the 1870 Census date, this can be adjusted.

### 2.3 Counted population

For each state:

$$
C_s = P_s \cdot q_s
$$

where:

- $P_s$ is the state population.
- $q_s$ is the modeled share of the state population in the counted pre-1870 stock.
- $C_s$ is the counterfactual census population used for reapportionment.

In the older first-pass model, $q_s$ could be one of:

- `primary_qualifying_ancestry_share`: share estimated to have majority pre-1870 ancestry.
- `any_qualifying_ancestor_share`: share estimated to have at least one pre-1870 ancestor.
- `average_qualifying_ancestry`: average fractional pre-1870 ancestry share.

For apportionment, the cleanest interpretation is usually the **stock count**, meaning:

$$
C_s = \text{modeled number of residents belonging to the pre-1870 stock}
$$

If using the earlier CSV, the closest available proxy is:

$$
C_s = P_s \cdot \texttt{primary\_qualifying\_ancestry\_share}_s
$$

---

## 3. Data inputs

### 3.1 Modern Census race and population data

The fetch script is configured to pull 2000, 2010, and 2020 decennial Census data.

For 2020 PL 94-171 data:

| Quantity | Census variable |
|---|---|
| Total population | `P1_001N` |
| Black or African American alone | `P1_004N` |
| American Indian and Alaska Native alone | `P1_005N` |

For 2000 and 2010 SF1 data:

| Quantity | Census variable |
|---|---|
| Total population | `P001001` |
| Black or African American alone | `P003003` |
| American Indian and Alaska Native alone | `P003004` |

The fetcher writes:

```text
data/modern_census_state_race_2000_2020.csv
data/modern_census_us_race_2000_2020.csv
```

These are not included unless the script is run with a Census API key.

### 3.2 Historical state-level data

The historical state-level panel should be supplied from NHGIS or another cleaned historical Census source:

```text
data/nhgis_historical_state_panel_1790_1990.csv
```

Expected columns:

```text
year,state,abbr,total,black,aian,foreign_born,native_parentage
```

Minimum required columns:

```text
year,state,abbr,total
```

The model improves when `black`, `aian`, `foreign_born`, and `native_parentage` are present.

### 3.3 Immigration data

The package includes:

```text
data/dhs_lpr_by_decade.csv
```

This stores gross lawful permanent resident admissions by decade. The model uses a net-migration adjustment:

$$
I_d = \lambda_d \cdot L_d
$$

where:

- $I_d$ is estimated net immigrant-entry mass in decade $d$.
- $L_d$ is gross LPR admissions in decade $d$.
- $\lambda_d$ is a net factor, e.g. 0.75.

The net factor is an assumption because LPR admissions are not identical to net migration. People leave, die, enter outside LPR channels, or change status after arrival.

### 3.4 Native American correction

Native American enumeration is a special problem because early censuses did not fully enumerate all Native people, especially those classified historically as "Indians not taxed."

The package includes:

```text
data/native_correction_notes.csv
```

The recommended modeling strategy is to include a sensitivity mode:

```text
native_mode = enumerated_only | corrected
```

A corrected mode can use an external series or 1890 taxed/untaxed Indian counts as an anchor/backcast.

---

## 4. National cohort model

The clean national version is a decade-stepped cohort accounting model.

Let:

- $M_c(t)$ be the mass at time $t$ of origin cohort $c$.
- $c = 1790$ for the initial resident stock.
- $c = d$ for immigrant-entry cohorts entering in decade $d$.
- $I_d$ be net immigrant entry in decade $d$.
- $P_t$ be total population at census year $t$.

The model initializes:

$$
M_{1790}(1790) = P_{1790}
$$

or, if using race-specific modules:

$$
M_{1790}^{\text{Black}}(1790),
\quad
M_{1790}^{\text{AIAN}}(1790),
\quad
M_{1790}^{\text{Other}}(1790)
$$

The updated inclusion policy counts Black and Native American pre-1870 stock:

$$
\text{counted}_{t}
=
\sum_{c \leq 1860} M_c(t)
+
\text{corrected AIAN pre-1870 stock if not already represented}
$$

Post-1870 immigrant cohorts are not counted as pre-1870 stock:

$$
\text{post1870}_{t}
=
\sum_{c > 1860} M_c(t)
$$

The counted share is:

$$
q_t = \frac{\text{counted}_t}{P_t}
$$

---

## 5. Natural increase residual

For each decade $d$, total population change can be decomposed as:

$$
P_{d+10} - P_d
=
N_d + I_d
$$

where:

- $N_d$ is natural increase: births minus deaths.
- $I_d$ is net immigration.

Therefore:

$$
N_d = P_{d+10} - P_d - I_d
$$

The model then applies a decennial growth rate to existing cohorts:

$$
g_d = \frac{N_d}{\sum_c M_c(d)}
$$

Then each existing cohort evolves as:

$$
M_c(d+10) = M_c(d)(1 + g_d)
$$

If using cohort-specific fertility or survival premiums, this becomes:

$$
M_c(d+10)
=
M_c(d)\left(1 + g_d + \pi_c(d)\right)
$$

where $\pi_c(d)$ is a cohort-specific premium or penalty. A positive premium for recent immigrant cohorts can approximate observed fertility differences, but this should be treated as a sensitivity parameter.

New immigrant cohorts enter as:

$$
M_d(d+10) = I_d
$$

A more careful version can enter them at mid-decade, but the decade-end approximation is usually adequate for this level of uncertainty.

---

## 6. State-level model

The state-level model should not simply apply the national share to every state. State estimates need state-specific historical populations and migration dynamics.

The ideal state equation is:

$$
C_{s,2020}
=
\sum_{c \leq 1860} M_{s,c}(2020)
$$

where $M_{s,c}(2020)$ is the 2020 descendant mass in state $s$ from origin cohort $c$.

A full version would require a state-to-state migration matrix by decade:

$$
M_{s,c}(d+10)
=
\sum_r T_{r \rightarrow s,d} \cdot M_{r,c}(d)(1 + g_{r,d})
$$

where:

- $T_{r \rightarrow s,d}$ is the share of people moving from state $r$ to state $s$ during decade $d$.
- $g_{r,d}$ is state-specific natural increase.

Because complete historical interstate migration matrices are difficult to reconstruct, the first-pass state model used state-level proxies:

$$
q_s
=
f(\text{foreign-born share}_s,\ \text{Black share}_s,\ \text{AIAN share}_s,\ \text{old-stock factor}_s,\ \text{fertility factor}_s)
$$

The updated preferred approach is:

1. Use real historical state total/race/nativity data from NHGIS.
2. Treat Black and Native American pre-1870 stock as included.
3. Use post-1870 immigrant-origin cohorts to subtract from total resident stock.
4. Run sensitivity scenarios for Native under-enumeration and net immigration.

---

## 7. Electoral College reapportionment

The Electoral College layer asks:

> If the census counted only $C_s$, how many electoral votes would each state have?

The House has 435 seats. The Huntington-Hill method gives every state one seat, then assigns remaining seats by priority value.

Each state starts with:

$$
H_s = 1
$$

For a state with counted population $C_s$ and current House seats $n$, the next-seat priority is:

$$
A_{s,n}
=
\frac{C_s}{\sqrt{n(n+1)}}
$$

The algorithm:

1. Give each state one House seat.
2. Compute $A_{s,1}$ for every state.
3. Award the next seat to the highest priority.
4. Recompute that state's priority using its new seat count.
5. Repeat until all 435 House seats are assigned.

Electoral votes are then:

$$
EV_s = H_s + 2
$$

For DC, the current package defaults to:

$$
EV_{DC} = 3
$$

A sensitivity option can exclude DC or keep it fixed.

The script writes:

```text
state,abbr,population,qualifying_share,counted_population,
actual_house_2024,hypothetical_house,house_change,
actual_ev_2024,hypothetical_ev,ev_change
```

---

## 8. How to run

### 8.1 Fetch static inputs

```bash
cd pre1870_reapportionment_package
pip install -r requirements.txt

python fetch_pre1870_inputs.py --write-static --validate
```

### 8.2 Fetch modern Census API inputs

```bash
export CENSUS_API_KEY="YOUR_CENSUS_KEY"

python fetch_pre1870_inputs.py --fetch-modern-census --validate
```

### 8.3 Show Census API query templates

```bash
python fetch_pre1870_inputs.py --show-queries
```

### 8.4 Run the existing first-pass reapportionment model

If `outputs/state_pre1870_estimates.csv` or a similar state estimate file exists:

```bash
python scripts/hypothetical_ec_reapportionment.py \
  --input outputs/state_pre1870_estimates.csv \
  --metric primary \
  --output-csv outputs/hypothetical_ec_reapportionment_primary.csv \
  --output-html outputs/hypothetical_ec_reapportionment_primary_map.html
```

Alternative metrics:

```bash
python scripts/hypothetical_ec_reapportionment.py --metric any
python scripts/hypothetical_ec_reapportionment.py --metric average
```

---

## 9. Validation checks

The package performs or recommends these checks:

1. 2024 electoral votes sum to 538.
2. The 50 states receive exactly 435 House seats.
3. DC is either fixed at 3 electors or explicitly excluded.
4. State populations sum close to national Census totals.
5. Race subtotals do not exceed total population.
6. Counted population satisfies: $0 \leq C_s \leq P_s$.
7. National counted share is plausible under sensitivity bounds.

---

## 10. Main limitations

### 10.1 Ancestry vintage is not directly observed

No Census asks whether a person's ancestors were present before 1870. The model reconstructs that using population, race, nativity, immigration, and cohort assumptions.

### 10.2 Native American under-enumeration

Native American population counts before the late nineteenth century are incomplete and politically defined. This is why the package treats Native inclusion as a correction/sensitivity problem.

### 10.3 Immigration data are not net migration

LPR admissions are gross admissions, not net immigration. A net factor is needed.

### 10.4 Interstate migration matters

State of residence in 2020 is not the same as state of ancestral residence. A rigorous state model needs interstate migration or a strong proxy.

### 10.5 Race categories change over time

Census race categories and definitions changed over time. Any long historical race series must harmonize categories carefully.

### 10.6 The model is not a voting model

The Electoral College map is only a reapportionment map. It does not estimate partisan outcomes or vote choice.

---

## 11. Recommended next improvement

The largest improvement would be to create this file from NHGIS:

```text
data/nhgis_historical_state_panel_1790_1990.csv
```

Then replace the first-pass state proxy shares with historical state cohort reconstruction.

A second major improvement would be to add a Native American correction table:

```text
data/native_correction_by_state_decade.csv
```

with columns:

```text
year,state,abbr,aian_corrected_population,source,notes
```

Then run at least three scenarios:

1. `native_mode = enumerated_only`
2. `native_mode = corrected_low`
3. `native_mode = corrected_high`

The final output should report electoral votes under all three sensitivity scenarios.
