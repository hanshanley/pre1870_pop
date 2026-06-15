# Assumptions and Sensitivity Parameters

## Model definition

**White Heritage American ancestry**: Descent from non-Black residents of the United States enumerated in the 1870 Census. The 1870 Census is the cutoff because it is the first post-Civil War census and the first to enumerate all residents regardless of race (though Native American enumeration remained incomplete).

**Excluded from qualifying stock**: Black Americans enumerated in 1870 (4,880,009 people, per Census POP-WP056). This is configurable via `--include-black-1870`.

**Included in qualifying stock**: All other 1870 residents, including foreign-born residents already present by 1870. This is configurable via `--exclude-1870-foreign-born`.

## National model parameters

| Parameter | Default | Range tested | Description |
|-----------|---------|-------------|-------------|
| `n_agents` | 300,000 | 100K-500K | Number of simulated agents |
| `immigration_flow_multiplier` | 1.15 | 1.00-1.30 | Scales gross LPR admissions to approximate total immigrant entries |
| `old_stock_fertility_multiplier` | 0.98 | 0.94-1.02 | Fertility weight for qualifying-ancestry parents |
| `nonqualifying_fertility_multiplier` | 1.03 | 1.00-1.08 | Fertility weight for non-qualifying parents |
| `random_mating_rate` | 0.35 | 0.20-0.55 | Fraction of parent pairs formed randomly vs. assortatively |

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
| 1870 Black population | Census POP-WP056 / NHGIS 1870_cPAX NT4 | 1870 | 4,880,009 |
| 1870 foreign-born share | Census POP-WP081 / NHGIS 1870_cPAX NT5 | 1870 | 14.4% |

## Known limitations

1. **Ancestry is not directly observed**. No Census asks whether a person's ancestors were present before 1870. The model reconstructs this using population, race, nativity, immigration, and cohort assumptions.

2. **Native American under-enumeration**. Native Americans were incompletely counted in early censuses. The model uses enumerated counts without correction. A sensitivity mode for corrected AIAN counts is planned but not yet implemented.

3. **Immigration data are gross admissions, not net migration**. The `immigration_flow_multiplier` parameter partially compensates, but undocumented immigration and emigration are not directly modeled.

4. **Interstate migration is simplified**. The agent model redistributes agents to match Census population targets but does not model geographic structure of migration (e.g., neighboring-state preference).

5. **Race categories change over time**. Census race categories evolved across decades. The NHGIS harmonization maps historical categories (slave/free colored, Negro, etc.) to a consistent "Black" column, but edge cases exist.

6. **1920/1930 foreign-born is White-only**. Census tables for these decades only separate nativity for the White population. Non-white foreign-born (< 1% nationally) is not captured.

7. **State-level fertility is not modeled**. The national TFR is applied uniformly to all states. State-specific fertility differences could affect results for high-fertility states (e.g., Utah).

8. **This is not a voting model**. The Electoral College map is a reapportionment exercise only. It does not estimate partisan outcomes or vote choice.

## NHGIS citation

Jonathan Schroeder, David Van Riper, Steven Manson, Katherine Knowles, Tracy Kugler, Finn Roberts, and Steven Ruggles. IPUMS National Historical Geographic Information System: Version 20.0 [dataset]. Minneapolis, MN: IPUMS. 2025. http://doi.org/10.18128/D050.V20.0
