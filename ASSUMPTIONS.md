# Assumptions and Sensitivity Parameters

## Model definition

**White Heritage American ancestry**: Descent from residents enumerated as **White**
in the 1870 Census. The 1870 Census is the cutoff because it is the first post-Civil
War census and the first to enumerate all residents regardless of race (though Native
American enumeration remained incomplete).

**Excluded from qualifying stock**: All non-white 1870 residents — Black Americans
(4,880,009), American Indian/Alaska Native (25,731 enumerated), and other non-white
races such as Chinese (~63,000) — plus all post-1870 immigrant cohorts and their
descendants. The qualifying source stock is the enumerated **White** 1870 population
(33,589,377; NHGIS `white` column), **not** `total − Black` (which would leave AIAN
and other non-white residents in the stock). Counting **all** 1870 residents
regardless of race (i.e. the full 1870 population) is available for sensitivity
comparison via `--include-nonwhite-1870`; doing so raises the 2020 majority share
from ~20–21% (White-only) to **~29% (national) / ~37% (state)** and the any-ancestor
share to ~61%.

**Included in qualifying stock**: White residents present by 1870, including
White foreign-born residents already in the U.S. by 1870. The foreign-born
treatment is configurable via `--exclude-1870-foreign-born`.

## National model parameters

| Parameter | Default | Range tested | Description |
|-----------|---------|-------------|-------------|
| `n_agents` | 300,000 | 100K-500K | Number of simulated agents |
| `immigration_flow_multiplier` | 1.15 | 1.00-1.30 | Scales gross LPR admissions to approximate total immigrant entries |
| `native_fertility_differential` | True | on/off | Use the cited per-decade foreign-born:native fertility ratio (see below) |
| `old_stock_fertility_multiplier` | 0.98 | 0.94-1.02 | Fallback fertility weight for qualifying parents (used only when the differential is off) |
| `nonqualifying_fertility_multiplier` | 1.03 | 1.00-1.08 | Fallback fertility weight for non-qualifying parents (used only when the differential is off) |
| `random_mating_rate` | 0.35 | 0.20-0.55 | Fraction of parent pairs formed randomly vs. assortatively |

## Fertility differential (native-born vs. immigrant), with sources

Immigrant-descended (non-qualifying) parents are weighted by the documented
foreign-born:native-born fertility ratio for each decade, loaded from
`data/fertility_by_nativity.csv` (not hardcoded). Old-stock fertility is
normalized to 1.0 and the non-qualifying weight is set to the cited ratio.

| Decade(s) | FB : native fertility ratio | Status | Source |
|-----------|------------------------------|--------|--------|
| 1870–1890 | 1.35 | **Assumption** (held flat to the cited 1900–1910 anchor; not independently measured) | anchored on the 1900–1910 citation below |
| 1900, 1910 | 1.35 | **Cited** (foreign-born white TFR ~35% higher than native-born white) | Michael R. Haines, white fertility by nativity, Historical Statistics of the United States: Millennial Edition (2006) |
| 1920–2000 | 1.33–1.35 | **Interpolated** between the cited 1910 and 2008 anchors (mid-century not independently measured) | — |
| 2010 (2008 ACS) | 1.33 | **Cited** (native TFR 2.07 vs immigrant 2.75) | Camarota & Zeigler, Center for Immigration Studies (2020), Census ACS |
| 2020 (2018 ACS) | 1.24 | **Cited** (native TFR 1.74 vs immigrant 2.15) | Camarota & Zeigler, CIS (2020), Census ACS |

Only the four **Cited** rows make a factual data claim, and each comes from a
primary source: the historical (1900–1910) anchor is the white fertility-by-nativity
series in Haines, *Historical Statistics of the United States: Millennial Edition*
(2006), and the modern (2008, 2018) anchors are total fertility rates by nativity
computed from the U.S. Census Bureau American Community Survey via the own-children
method. The exact historical ratio (~1.35) reflects the ~35% native/foreign-born
white differential reported for that period and was not independently re-derived
from the paywalled Millennial Edition tables. The 1870–1890 values are an explicit
assumption and 1920–2000 are interpolations between the cited anchors — both flagged
in the `basis` column of `data/fertility_by_nativity.csv`. No absolute TFRs are
asserted for non-cited years.

**Application caveat:** the cited ratios are a *first-generation* foreign-born vs.
native differential, but the model applies them to the whole immigrant-descended
(non-qualifying) lineage each decade. Because later immigrant generations converge
to native fertility, this is an upper bound on fertility-driven dilution. It is
adopted as the central case because it uses the cited per-decade native-vs-immigrant
fertility differential (`data/fertility_by_nativity.csv`) rather than the unsourced
fallback constants; turning it off (`old_stock`/`nonqualifying` constants)
raises the national majority share from ~20% to ~35%.

## State agent-based model

The state model uses the same agent mechanics as the national model but tracks agents across states. Key assumptions:

- **Immigration allocation**: Immigrants are distributed to states proportionally to each state's foreign-born population (from NHGIS historical data).
- **Internal migration**: Agents are redistributed between states each decade to match observed Census state population targets. Out-migrants are randomly sampled from excess states and reassigned to deficit states.
- **Mating**: Within-state only. Parents are sampled from the same state's agent pool.
- **No calibration**: Unlike the reduced-form model, the agent model is not calibrated to national anchors. State results emerge from the simulation.

## Data sources

| Data | Source | Years | Notes |
|------|--------|-------|-------|
| National population totals | Census POP-WP056 | 1870-1990 | Cross-checked against NHGIS state sums |
| National population totals | Census API (dec/sf1, dec/pl) | 2000-2020 | |
| State population, race, nativity | IPUMS NHGIS extracts | 1790-1990 | 100% count data where available |
| State population, race | Census API (dec/sf1, dec/pl) | 2000-2020 | |
| State foreign-born, Black-alone | Census ACS 5-year (B05002, B02001) | 2022 | Used by reduced-form model only |
| Immigration admissions | DHS/OHSS Yearbook Table 1 | 1820-2010 | Gross LPR admissions by decade |
| Total fertility rate | Haines Ab1-10 (historical), NCHS (modern) | 1870-2020 | National TFR applied to all states |
| Fertility by nativity | Haines, white fertility by nativity (HSUS Millennial Ed. 2006) for 1900-10; Census ACS own-children TFR by nativity (2008, 2018) | 1870-2020 | `data/fertility_by_nativity.csv`; FB:native fertility ratio by decade (cited anchors + flagged interpolation) |
| 1870 White population | Census POP-WP056 / NHGIS 1870_cPAX NT4 White | 1870 | 33,589,377 (qualifying stock) |
| 1870 Black population | Census POP-WP056 / NHGIS 1870_cPAX NT4 | 1870 | 4,880,009 (excluded) |
| 1870 foreign-born share | Census POP-WP081 / NHGIS 1870_cPAX NT5 | 1870 | 14.4% |

## Known limitations

1. **Ancestry is not directly observed**. No Census asks whether a person's ancestors were present before 1870. The model reconstructs this using population, race, nativity, immigration, and cohort assumptions.

2. **Native American treatment**. Native Americans enumerated in 1870 are excluded from the White Heritage qualifying stock (along with Black and other non-white residents), so AIAN under-enumeration in early censuses no longer biases the qualifying numerator — it only slightly affects the 1870 denominator. Early-census AIAN counts remain incomplete and politically defined.

3. **Immigration data are gross admissions, not net migration**. The `immigration_flow_multiplier` parameter partially compensates, but undocumented immigration and emigration are not directly modeled.

4. **Interstate migration is simplified**. The agent model redistributes agents to match Census population targets but does not model geographic structure of migration (e.g., neighboring-state preference).

5. **Race categories change over time**. Census race categories evolved across decades. The NHGIS harmonization maps historical categories (slave/free colored, Negro, etc.) to a consistent "Black" column, but edge cases exist.

6. **1920/1930 foreign-born is White-only**. Census tables for these decades only separate nativity for the White population. Non-white foreign-born (< 1% nationally) is not captured.

7. **State-level fertility is not modeled**. The national TFR is applied uniformly to all states. State-specific fertility differences could affect results for high-fertility states (e.g., Utah).

8. **This is not a voting model**. The Electoral College map is a reapportionment exercise only. It does not estimate partisan outcomes or vote choice.

## NHGIS citation

Jonathan Schroeder, David Van Riper, Steven Manson, Katherine Knowles, Tracy Kugler, Finn Roberts, and Steven Ruggles. IPUMS National Historical Geographic Information System: Version 20.0 [dataset]. Minneapolis, MN: IPUMS. 2025. http://doi.org/10.18128/D050.V20.0
