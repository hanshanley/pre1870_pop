# How the model works

A plain-language walkthrough of the headline **state** model
(`scripts/state_agent_ancestry_model.py`): how the **agent budget** is spent, how
the **Monte-Carlo simulation** runs decade by decade, and how the ancestry
**"tree"** is tracked to estimate each person's pre-1870 White heritage. A
**national** companion model (`scripts/pre1870_ancestry_model.py`) shares the same
mechanics on one well-mixed population; [§7](#7-two-agent-based-models-and-why-they-differ)
explains how the two relate and why their headline shares form a range, not a
single number.

This document explains the *code*. For the formal math see
[MATH_AND_METHODS.md](MATH_AND_METHODS.md); for the input assumptions and their
sources see [ASSUMPTIONS.md](ASSUMPTIONS.md).

---

## 1. The one idea behind everything: the ancestry fraction `q`

Every simulated person ("agent") carries a single number, **`q` between 0 and 1**:

> `q` = the fraction of that person's ancestry that traces back to residents who
> were enumerated as **White in the 1870 Census** (the "White Heritage American"
> source stock).

- `q = 1` → all of this person's ancestors were pre-1870 White residents.
- `q = 0` → none were (e.g. descended entirely from post-1870 immigrants).
- `q = 0.5` → half of their family tree traces to the pre-1870 White stock.

Everything the model reports is just a summary of the `q` values of the people
alive in a state in 2020:

| Reported metric | Definition in code | Meaning |
|---|---|---|
| `average_qualifying_ancestry` | `mean(q)` | average heritage fraction |
| `any_qualifying_ancestor_share` | `mean(q > ~0)` | share with **any** pre-1870 White ancestor |
| `primary_qualifying_ancestry_share` | `mean(q > 0.5)` | share whose ancestry is **majority** pre-1870 White |

The national headline numbers (≈ **21% majority / 56% any** in 2020) come from the
**national** companion model (`pre1870_ancestry_model.py`), which runs these same
agent mechanics on one well-mixed national population. The state model's
population-weighted average is close but not identical (**≈ 20% majority / 54% any**);
see [§7](#7-two-agent-based-models-and-why-they-differ) for why the two differ.

---

## 2. The budget: how agents are spread across states

We do **not** simulate 330 million people — that would be slow and unnecessary.
Instead we simulate a fixed **budget** of agents (default **1,000,000**) and treat
each agent as a representative sample of many real people.

`allocate_agents_to_states()` spends that budget like this:

1. **Proportional to population.** Each state gets a share of the budget equal to
   its share of the Census population that decade. California (big) gets far more
   agents than Wyoming (small).
2. **With a floor.** Every state is guaranteed at least
   `min_agents_per_state` agents (default **500**), so even tiny states have
   enough sample to estimate a stable share.
3. **Conserved.** The leftover from rounding is handed to the largest state so the
   per-state counts always add up to exactly the total budget.

The budget is **re-allocated every decade** to match that decade's real Census
populations. When a state's population share grows or shrinks, its agent count
follows — and that mismatch is exactly what drives the **internal-migration** step
(agents are moved from over-full states to under-full states each decade).

**Why the floor matters (precision).** A state's estimate is a sample average, so
its Monte-Carlo error is roughly `sqrt(p(1-p) / n_state)`. The floor caps the
worst case: at 500 agents the per-state error is about **2.2 pp** at the worst
(p = 0.5), versus about **7 pp** at the old floor of 50. It "borrows" a negligible
slice of the budget (at most 51 × 500 agents) and introduces **no bias** — each
state is still estimated only from its own agents.

---

## 3. The simulation: marching from 1870 to 2020

### Step 0 — Seed the year 1870

For each state, every agent is given `q = 1` with probability equal to that
state's **enumerated White share in 1870** (read from the NHGIS panel), and `q = 0`
otherwise. So a state that was 90% White in 1870 starts with ~90% of its agents at
`q = 1`. Black, American Indian/Alaska Native, and other non-white 1870 residents
are **excluded** from the source stock (they are `q = 0`) but still count in the
modern population denominator.

### Steps 1880 → 2020 — one decade at a time

Each decade the population of every state is rebuilt from three groups:

```
next population  =  carry-over residents  +  newborn children  +  new immigrants
```

1. **Carry-over.** A fraction of the existing residents persist into the next
   decade. The newborn fraction (`turnover`) is derived from the decade's total
   fertility rate (`turnover_from_tfr`): high 19th-century fertility replaces
   more of the population per decade (~37%), low modern fertility less (~25%).

2. **Newborn children — this is the "tree".** See section 4 below. Children
   inherit a blend of two parents' `q` values.

3. **Immigrants.** New arrivals enter with **`q = 0`** (no pre-1870 White
   ancestry). How many arrive is set by the decade's recorded immigration
   (LPR admissions ÷ population, scaled by `immigration_flow_multiplier`, capped
   at 25%). They are distributed to states in proportion to each state's
   foreign-born population, so immigration lands where the Census says it did.

4. **Internal migration.** Finally, agents are shuffled between states so each
   state's agent count matches its real Census population for that decade
   (over-full states release agents into a pool; under-full states draw from it).

After 2020 the model reads off each state's `q` distribution and computes the
three metrics in the table above.

---

## 4. The "tree": how children inherit heritage

This is the heart of the model (`draw_parents()` in
`scripts/pre1870_ancestry_model.py`). For every newborn child:

1. **Pick two parents** from the current state population. Parent selection is
   weighted by fertility, using the **cited per-decade immigrant:native fertility
   ratio** (`data/fertility_by_nativity.csv`) — so in decades when immigrant
   families had more children, low-`q` parents are slightly more likely to be
   chosen.

2. **Pair them by mating pattern.** A fraction of pairings
   (`random_mating_rate`, default 0.35) are **random** across the whole state; the
   rest are **assortative** — the second parent is drawn from the same ancestry
   "bin" as the first (none / low / medium / high `q`). Assortative mating keeps
   high-heritage and low-heritage lines from blending into everyone at once, which
   pure random mating would unrealistically cause within a few generations.

   > **Where does 0.35 come from?** It is an **explicit modeling assumption, not a
   > measured statistic** — there is no dataset of "fraction of US couples who
   > mate randomly vs. within ancestry," so this is not pulled from a source. It is
   > a deliberately middling value chosen on principle: pure random mating
   > (`1.0`) would unrealistically diffuse trace ancestry to nearly everyone within
   > a few generations, while pure assortative mating (`0.0`) would freeze
   > ancestry groups apart forever; real populations sit in between, so we use a
   > value below the midpoint that admits substantial mixing without total
   > blending.
   >
   > Crucially, we **tested how much it matters** rather than just asserting it.
   > Sweeping `random_mating_rate` across its **full 0.0–1.0 range moves the
   > headline majority share by less than ~1 point (21.2%–22.2%)**, so the choice
   > is near-irrelevant to the main result; it mainly shapes the broader
   > "any ancestor" diffusion. The sensitivity analysis
   > (`--sensitivity`) varies it over 0.20 / 0.35 / 0.55, and the parameter and its
   > range are listed in [ASSUMPTIONS.md](ASSUMPTIONS.md). This is the honest
   > status: a defensible but un-sourced assumption whose impact has been measured
   > and shown to be small.

3. **The child's value is the midpoint of its parents:**

   ```
   q_child = 0.5 * (q_parent1 + q_parent2)
   ```

This simple midpoint rule is what makes `q` behave like a real family tree.
Unfold it across generations and a person's `q` is exactly:

> the **share of their genealogical ancestors** (½ from each parent, ¼ from each
> grandparent, ⅛ from each great-grandparent, …) who were pre-1870 White
> residents.

So `q` is not a vague "score" — it is, by construction, the fraction of a person's
ancestry tree that traces to the 1870 White source stock. That is precisely the
quantity the project sets out to estimate.

### Where the fertility differential comes from

The per-decade immigrant:native fertility ratio in `data/fertility_by_nativity.csv`
is **not invented** — every row is tagged in its `basis`/`source` columns as one of
**CITED**, **INTERPOLATED**, or **ASSUMPTION**, and traces to two published anchors:

| Decade(s) | Ratio | Where it comes from |
|---|---|---|
| **1900–1910** (CITED) | 1.35 | Michael R. Haines, *white total fertility rate by nativity*, **Historical Statistics of the United States: Millennial Edition** (Cambridge Univ. Press, 2006). Foreign-born white TFR ran ~⅓ above native-born white. |
| **2008** → 2010 slot (CITED) | 1.33 | U.S. Census Bureau **American Community Survey (2008)**, TFR by nativity via the own-children method: native **2.07** vs immigrant **2.75**. Computation by Camarota & Zeigler, **Center for Immigration Studies (2020)**. |
| **2018** → 2020 slot (CITED) | 1.24 | U.S. Census Bureau **ACS (2018)**, same method: native **1.74** vs immigrant **2.15**. Same CIS (2020) report. |
| **1870–1890** (ASSUMPTION) | 1.35 | Held flat at the 1900–1910 Haines anchor — no nativity-specific fertility series exists this far back. |
| **1920–2000** (INTERPOLATED) | 1.34→1.33 | Linearly interpolated between the 1910 Haines anchor and the 2008 ACS anchor; mid-century values are not independently measured. |

Sources (also stored in the CSV's `source_url` column):

- Haines, *Fertility and Mortality in the United States*:
  <https://eh.net/encyclopedia/fertility-and-mortality-in-the-united-states/>
- U.S. Census Bureau ACS: <https://www.census.gov/programs-surveys/acs>
- Camarota & Zeigler, CIS (2020):
  <https://cis.org/Report/Immigrant-and-NativeBorn-Fertility-2008-2018>

Only the **two endpoints (Haines ~1910 and ACS/CIS 2008 & 2018) are independently
measured**; the pre-1900 and mid-century rows are explicitly flagged as held-flat or
interpolated, so a reader can see exactly which numbers are data and which are
bridging assumptions. (See also [ASSUMPTIONS.md](ASSUMPTIONS.md).)

---

## 5. Monte-Carlo: why we run it several times

The simulation uses randomness in many places (who starts at `q = 1`, which
parents are chosen, who migrates). Any single run is therefore one **random
realization** — a sample, not an exact answer. Two controls manage this:

- **`--n-agents`** — more agents ⇒ less sampling noise. Error shrinks like
  `1/sqrt(agents)` (4× the agents ≈ half the noise).
- **`--seeds`** — the model runs once per seed and **averages** the results
  (`run_multi_seed`). Averaging `k` seeds shrinks the reported noise like
  `1/sqrt(k)`, and the **spread across seeds gives an honest error estimate** that
  a single run cannot.

Both knobs only reduce **variance**, never **bias** — they make the estimate
converge faster onto *the model's own answer*. They cannot fix uncertainty that
comes from the model's assumptions (e.g. `immigration_flow_multiplier`), which is
the larger, systematic source of uncertainty discussed in
[ASSUMPTIONS.md](ASSUMPTIONS.md).

### Measured precision at the defaults (1M agents, 5 seeds, floor 500)

| Quantity | Value |
|---|---|
| Per-state std-dev across seeds (single seed) | median ≈ **0.9 pp**, worst ≈ 4.4 pp (smallest states) |
| Reported estimate's error (5-seed mean) | median ≈ **0.4 pp**, worst ≈ 2.0 pp |

That is comfortably below the multi-point systematic uncertainty, so adding still
more agents would buy precision finer than the model itself is accurate — there is
no point chasing it.

---

## 6. Where to look in the code

| What | Location |
|---|---|
| Agent budget / allocation | `allocate_agents_to_states()` |
| 1870 seeding from White share | `simulate_states()`, the "Initialize at 1870" block |
| Decade loop (carry / births / immigrants / migration) | `simulate_states()`, the "Decade loop" block |
| The inheritance tree (`q_child = midpoint`) | `draw_parents()` in `pre1870_ancestry_model.py` |
| Fertility → turnover | `turnover_from_tfr()` |
| Cited fertility differential | `decade_fertility_multipliers()` + `data/fertility_by_nativity.csv` |
| Multi-seed averaging | `run_multi_seed()` |
| Tunable parameters (with rationale comments) | `StateAgentModelParams` dataclass |

---

## 7. Two agent-based models, and why they differ

There are **two** agent-based simulations in this package. They share the same
core mechanics (the `q` fraction, fertility-weighted births, the `q_child =
midpoint` tree, the cited fertility differential) but differ in geographic
resolution:

| Model | File | Population | Used for |
|---|---|---|---|
| **National** | `pre1870_ancestry_model.py` | one well-mixed national pool | national time-series & headcount figures; the headline national share |
| **State** | `state_agent_ancestry_model.py` | 50 states + DC, simulated separately with internal migration | the state map, the EC reapportionment, and a population-weighted national check |

**They agree closely on the White-only headline:**

| Metric (2020, White-only stock) | National | State (pop-weighted) |
|---|---|---|
| Majority (>50%) ancestry | **21.2%** | **19.8%** |
| Any pre-1870 ancestor | **56.0%** | **53.7%** |
| Average ancestry (mass) | **28.9%** | **27.2%** |

So the defensible headline is a **range, ~20–21% majority / ~54–56% any**, not a
single false-precision number. The state model reads slightly lower because it keeps
lineages **regionally concentrated** — mating happens within a state, so high- and
low-heritage populations blend more slowly than in the single national pool.

### Sensitivity: counting all 1870 races as qualifying stock

Both models expose `--include-nonwhite-1870`, which seeds the qualifying stock from
the **entire** enumerated 1870 population (White, Black, AIAN, Chinese — every race
present then) instead of White residents only:

| Metric (2020, **all-race** 1870 stock) | National | State (pop-weighted) |
|---|---|---|
| Majority (>50%) ancestry | **29.2%** | **37.4%** |
| Any pre-1870 ancestor | **60.5%** | **61.7%** |
| Average ancestry (mass) | **35.8%** | **42.2%** |

Here the two models diverge **more** (majority share **~29–37%**). The reason is
geography: in 1870 the Black population was ~88% concentrated in the South. The
**national** model dilutes those lineages into one national pool, while the
**state** model lets them compound within Southern states across 15 decades of
mostly within-state mating — so the state estimate runs substantially higher. The
wider spread is itself the honest signal that this counterfactual is more
geographically sensitive than the White-only headline.
