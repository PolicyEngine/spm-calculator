# CE in-kind benefit imputation

BLS adds five imputed in-kind benefits to each consumer unit's
out-of-pocket FCSUti before it estimates SPM thresholds: school lunch
(NSLP), WIC, LIHEAP, broadband subsidies and rental assistance. It leaves
SNAP out because it assumes households spend SNAP's EBT benefits like
cash, so reported food spending already includes them
([BLS SPM thresholds page](https://www.bls.gov/pir/spmhome.htm)). The
package's [CE replication](current-ce-replication.md) omits all five by
default. This page documents an optional research stage that imputes
them, and measures how much they explain of the replication's gap to
BLS's corrected thresholds and of threshold growth.

The stage leaves the default replication alone. It composes the public
stages of `spm_calculator.ce_threshold` without editing that module, so
the September 8, 2026 replication receipt and the code identities that
seal the [canonical forecasts](rolling-forecasts.md) all stay valid.

## Run it

The imputation needs SciPy, which the `inkind` extra installs:
`uv pip install "spm-calculator[inkind]"`, or `uv sync --extra inkind`
in a checkout. `ce_units` comes from `ce_inkind.ce_unit_covariates` and
`cps_donors` from `cps_asec.load_household_donors`.

```python
from spm_calculator.ce_inkind import InKindConfig, impute_in_kind
from spm_calculator.ce_inkind_stage import (
    prepare_out_of_pocket,
    replicate_with_in_kind,
)

run = prepare_out_of_pocket(
    ce_window, 2025, youth_policy="exclude_unresolved", cpi_series=cpi
)
imputation = impute_in_kind(ce_units, cps_donors, InKindConfig(implicates=5))
result = replicate_with_in_kind(run, imputation.for_target(0, 2025))
result["thresholds"], result["out_of_pocket"]["thresholds"]
```

`scripts/replicate_ce_inkind.py` builds `ce_units` and `cps_donors` from
cached CE Interview bundles (2014–2024) and CPS ASEC public-use files
(2015–2025), runs 2019–2025 with and without the stage, repeats both with
BLS's FCSUti index as the deflator, and writes
`spm_calculator/data/current/ce_inkind_replication_2019_2025.json`. It
makes no network requests. It stops with an error unless the
out-of-pocket run matches the archived receipt exactly and an all-zero
in-kind table reproduces that run exactly.

## Method

BLS has not published its imputation code or covariates, so the models
here follow its method text, the Census SPM technical documentation that
BLS cites for benefit values, and USDA program data. Each threshold year
T uses CE collection quarters (T−5)Q2 through TQ1. A collection quarter
(y, q) covers reference year y when q ≥ 2 and y − 1 when q = 1, and the
imputation for reference year r draws donors from the CPS ASEC of survey
year r + 1.

| Component | Participation | Value | Enters |
|---|---|---|---|
| School lunch (NSLP) | Logit on CPS households with a member aged 5–18 (`HFLUNCH`). The CE universe applies only the age rule, as BLS does. | Hot deck from participating CPS households in the same state, SNAP, below-150%-of-poverty and child-count cell (widening to region, then the nation, when a cell has too few donors), scaled to the CE unit's children aged 5–18. Donor values: Census's `SPM_SCHLUNCH` for reference years 2018 onward; for earlier years, the traditional formula (USDA reimbursement plus donated-food value per lunch, weighted 5/9 spring and 4/9 fall school year, times 179 days, for each child receiving lunch; free below 150% of the official poverty line, otherwise free or reduced with equal probability). | FCSUti |
| WIC | Logit on CPS households in the WIC universe | Census's participant rule (all children under 5, plus the mother of a child aged 0–1, otherwise one pregnant woman) × 12 × USDA's national fiscal-year average monthly food cost. Zero where the state finished WIC EBT before the middle of the reference period. | FCSUti |
| LIHEAP | Logit on all CPS households | Predictive mean matching on household-reported `HENGVAL` | FCSUti and SU |
| Broadband (EBB, ACP) | Logit on all CPS households, reference years 2021 onward | Predictive mean matching on Census's assigned `SPM_BBSUBVAL` | FCSUti |
| Rental assistance | CE renters reporting `GOVTCOST` or `PUBLHOUS` in the rent file | Weighted Tobit of log monthly rent on unit characteristics, with assisted units censored from above at their rent paid. Benefit = 12 × (imputed market rent − rent paid). | FCSUti and SU |

Participation models share one covariate set that both surveys measure:
income relative to the official poverty threshold, SNAP, public
assistance, SSI and housing-assistance receipt, tenure, household size,
counts of children under 5, children aged 5–18, members 65 and over and
earners, and the reference person's age, sex, race, Hispanic origin and
education. Each model uses state indicators where the CE identifies the
state, region indicators where it identifies only the region, and neither
otherwise. Census's school lunch values carry its COVID-era methods for
virtual schooling and P-EBT (Shrider 2021, 2022, 2023), which BLS also
says it follows, and its later universal-free-meal and Summer EBT rules.

The WIC universe follows BLS: a woman aged 15–45, or a child under 5 with
a woman aged 15 or older. From the 2025 thresholds BLS drops the woman
requirement for units with children under 5, so `for_target` applies the
older rule to earlier targets. Every state and DC finished WIC EBT by
October 2022 (USDA WIC EBT status, in `data/inkind/`), so WIC adds nothing
from reference year 2023.

The rental model fits renters per reference year: unassisted units with
rent of at least $50 a month enter as observed, assisted units as
censored at their rent paid. Covariates cover bedrooms, bathrooms,
building type, urbanicity, population size, state (or region where the
CE suppresses the state) and quarter. Each assisted unit's market rent is
a draw from the fitted distribution above its rent paid.

Five implicates draw the logit, matching-regression and Tobit parameters
from their estimated sampling distributions (proper multiple imputation),
and each implicate draws its own school lunch donors. Unit-level draws
hash the unit's `NEWID` with the seed, the component and the implicate;
parameter draws seed from the component, reference year and implicate.
Models fit on rows sorted by key, so results do not depend on row order
and repeat exactly.

### Where the amounts enter

Every component enters FCSUti. LIHEAP and rental assistance pay for
utilities and shelter, so they also enter SU, which sets the
tenure-specific part of each threshold,
`0.82 × (1.2 × FCSUti_E − SU_E + SU_Eh)`. The stage carries reference-year
amounts to the threshold year with the price factor the replication
applies to the same unit's out-of-pocket spending, and keeps the CPI
component weights of out-of-pocket spending.

The stage never lowers any unit's FCSUti or SU, yet a single component
can still lower a tenure's threshold slightly: added benefits reorder
units and change which of them land in the 47th–53rd percentile band.
In 2025, WIC alone lowers the renter threshold by 0.03% and broadband
alone by 0.04%.

## Invariants

1. Imputed amounts are finite and nonnegative for every unit and
   component.
2. The stage never lowers any unit's FCSUti or SU.
3. An all-zero in-kind table reproduces the out-of-pocket thresholds,
   estimation diagnostics and normalized expenditures exactly. The default
   replication runs no in-kind code.
4. Imputation repeats exactly and does not depend on row order.
5. Units outside a component's universe get zero: school lunch needs a
   member aged 5–18, WIC needs the universe and a state without complete
   EBT, broadband needs reference year 2021 or later, and rental
   assistance needs an assisted renter.
6. Growth factors exactly into price × real out-of-pocket × in-kind, and
   the additive contributions sum to total growth.

`tests/test_ce_inkind.py` checks each on synthetic CE and CPS data:
Hypothesis property tests cover invariants 1, 2, 3 and 6, and fixture
tests cover 4 and 5. It also compares the USDA lunch formula with
the values Census assigned in 2018 and 2019 (the formula gives
$626.35/$554.75 against Census's $627/$555, and $642.71/$571.11 against
$643/$571), checks that the logit and Tobit recover known parameters,
and fails when the committed receipt no longer matches the code that
produced it.

## Results

All figures come from the committed receipt, five implicates, with CPI
pinned to the package's `cpi_annual.json` unless a section says
otherwise. The CE estimation sample is consumer units with children.

In short:

- Imputed benefits lift the replication's thresholds by 1.1–3.9% and
  carry them above BLS's corrected levels for every tenure in every year
  from 2019 to 2025.
- They change 2022–2025 threshold growth by −0.6 to +1.0 points.
- The price index matters more. Deflating with BLS's FCSUti index instead
  of the package's composite CPI adds 0.9–2.0 points of 2022–2025 growth
  and brings the replication without the stage within 0.7 points of
  BLS's growth for every tenure.

### Imputed amounts

Mean amount per consumer unit in the estimation sample, in threshold-year
dollars:

| Target | School lunch | WIC | LIHEAP | Broadband | Rental assistance | Total | Share with any |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2019 | 319 | 51 | 17 | 0 | 439 | 826 | 33.8% |
| 2020 | 342 | 43 | 18 | 0 | 438 | 840 | 34.4% |
| 2021 | 333 | 33 | 18 | 0 | 450 | 834 | 33.1% |
| 2022 | 425 | 25 | 21 | 2 | 484 | 957 | 36.4% |
| 2023 | 509 | 16 | 24 | 5 | 477 | 1,031 | 38.6% |
| 2024 | 552 | 9 | 25 | 9 | 504 | 1,099 | 39.9% |
| 2025 | 587 | 3 | 25 | 11 | 530 | 1,156 | 41.1% |

School lunch and rental assistance supply over 90% of the total in every
year. School lunch grows the most, from $319 to $587 a unit. Among CPS
households with school-age children, reported participation rises from
33% in reference year 2014 to 54% in 2021, then falls back to 49% in
2024, while the mean donor value per participating household rises from
$989 (2014, USDA formula) to $1,388 (2024, Census values).

The CE imputation tracks its CPS donors. Weighted participation, CE
imputed against CPS donors, by reference year:

| Component | 2014 | 2018 | 2021 | 2024 |
|---|---|---|---|---|
| School lunch (households with a member 5–18) | 33.9% / 33.2% | 38.1% / 37.2% | 54.5% / 53.7% | 47.7% / 48.6% |
| WIC (WIC universe) | 7.3% / 7.5% | 5.9% / 5.5% | 4.9% / 4.8% | 5.5% / 5.4% |
| LIHEAP (all) | 3.4% / 3.5% | 3.3% / 3.2% | 3.3% / 3.2% | 3.4% / 3.3% |
| Broadband (all) | — | — | 1.8% / 1.7% | 2.6% / 2.4% |

Rental assistance comes from the CE itself: 12.7% of CE renters report
assistance in 2014 and 14.0% in 2024, with mean annual benefits of $7,389
and $12,439 per assisted unit.

### Levels: gap to BLS's corrected thresholds

Signed gap from BLS's corrected thresholds in percent, without → with the
stage:

| Target | Renter | Owner with mortgage | Owner without mortgage |
|---|---:|---:|---:|
| 2019 | −1.12 → +1.67 | −1.67 → +0.85 | −1.00 → +2.85 |
| 2020 | −1.45 → +1.24 | −1.69 → +0.95 | −0.24 → +3.53 |
| 2021 | −1.36 → +1.75 | −1.55 → +0.81 | +0.78 → +3.06 |
| 2022 | −1.33 → +2.23 | −1.41 → +1.25 | +1.67 → +3.30 |
| 2023 | −1.07 → +1.42 | −2.05 → +1.08 | +0.72 → +3.01 |
| 2024 | −1.40 → +1.67 | −2.25 → +0.74 | +1.14 → +2.23 |
| 2025 | −2.77 → +0.25 | −1.79 → +0.92 | +0.11 → +2.54 |

The without column matches the [September 8 replication](current-ce-replication.md)
exactly. In-kind lift (percent of the out-of-pocket threshold), with the
between-implicate standard deviation in percent of the threshold:

| Target | Renter | Owner with mortgage | Owner without mortgage |
|---|---:|---:|---:|
| 2019 | 2.82 (0.15) | 2.56 (0.24) | 3.89 (0.12) |
| 2020 | 2.73 (0.23) | 2.69 (0.22) | 3.77 (0.22) |
| 2021 | 3.15 (0.18) | 2.40 (0.22) | 2.27 (0.33) |
| 2022 | 3.60 (0.25) | 2.70 (0.21) | 1.61 (0.34) |
| 2023 | 2.51 (0.14) | 3.20 (0.13) | 2.27 (0.99) |
| 2024 | 3.11 (0.20) | 3.06 (0.15) | 1.08 (0.69) |
| 2025 | 3.10 (0.34) | 2.76 (0.08) | 2.43 (0.86) |

Share of the gap the stage closes, `(with − without) / (BLS − without)`.
Values above 1 overshoot; negative values mean the replication already
exceeded BLS and the stage moves it further above. A dash marks gaps
under 0.5%, where the ratio means little.

| Target | Renter | Owner with mortgage | Owner without mortgage |
|---|---:|---:|---:|
| 2019 | 2.49 | 1.51 | 3.85 |
| 2020 | 1.85 | 1.56 | — |
| 2021 | 2.28 | 1.52 | −2.93 |
| 2022 | 2.67 | 1.89 | −0.98 |
| 2023 | 2.33 | 1.53 | −3.17 |
| 2024 | 2.20 | 1.33 | −0.96 |
| 2025 | 1.09 | 1.52 | — |

Without the stage, the replication runs 1.07–2.77% below BLS for renters
and 1.41–2.25% below for owners with mortgages in every year. The stage
lifts thresholds by 2.40–3.60% for those two groups, so both land above
BLS in every year: renters by 0.25–2.23% and owners with mortgages by
0.74–1.25%. Owners without mortgages already sit above BLS in five of
seven years, and the stage moves them to 2.23–3.53% above.

The imputed benefits therefore exceed the gap they might explain. Two
cautions limit what the level comparison shows. BLS's FCSUti also
includes home internet spending, which the replication omits because the
FMLI file has no internet summary, so the out-of-pocket gap mixes both
omissions. The replication's other approximations (annual CPI, the food
allocation, the percentile convention and sample policies) move levels
too. This comparison cannot tell whether BLS imputes smaller amounts or
whether those approximations push the replication up.

Component lifts, each component alone, in percent of the out-of-pocket
threshold:

| Component | 2022 renter | 2022 with mortgage | 2022 without mortgage | 2025 renter | 2025 with mortgage | 2025 without mortgage |
|---|---:|---:|---:|---:|---:|---:|
| School lunch | +1.28 | +1.40 | +0.13 | +1.36 | +1.31 | +1.93 |
| WIC | +0.10 | +0.07 | −0.20 | −0.03 | −0.03 | +0.17 |
| LIHEAP | +0.12 | +0.03 | −0.08 | +0.03 | +0.04 | +0.28 |
| Broadband | +0.02 | +0.01 | +0.02 | −0.04 | +0.00 | +0.36 |
| Rental assistance | +2.41 | +1.32 | +0.74 | +1.96 | +1.23 | +1.22 |

School lunch and rental assistance account for nearly all of the lift.
The components interact through band composition, so they do not sum to
the total.

### Growth, 2022 to 2025

Write `F(d, k, p)` for the threshold from the window of target year `d`,
with the stage off (`k = 0`) or on (`k = 1`), in prices of year `p`.
Growth of the full replication factors exactly as

```text
F(2025,1,2025) / F(2022,1,2022) = price × real × in_kind
real    = [F(2025,0,2025) / F(2022,0,2022)] / price
in_kind = [F(2025,1,2025) / F(2025,0,2025)] / [F(2022,1,2022) / F(2022,0,2022)]
```

with `price` either BLS's FCSUti index ratio (146.712 / 128.478, +14.19%)
or the package's composite CPI, `F(2022,0,2025) / F(2022,0,2022)`. The
in-kind factor does not depend on the price measure. Additive
contributions use the sequential split
`(price − 1) + price × (real − 1) + price × real × (in_kind − 1)`, which
sums to total growth.

| Tenure | BLS corrected | Without stage | With stage | Price | Real out-of-pocket | In-kind (implicate SD) |
|---|---:|---:|---:|---:|---:|---:|
| BLS FCSUti index | | | | | | |
| Renter | +22.15% | +20.37% | +19.78% | 14.19 | 6.18 | −0.58 (0.59) |
| Owner with mortgage | +21.61% | +21.15% | +21.22% | 14.19 | 6.96 | +0.07 (0.35) |
| Owner without mortgage | +20.63% | +18.79% | +19.75% | 14.19 | 4.59 | +0.96 (0.86) |
| Package composite CPI | | | | | | |
| Renter | | | | 13.25 | 7.12 | −0.58 (0.59) |
| Owner with mortgage | | | | 13.12 | 8.03 | +0.07 (0.35) |
| Owner without mortgage | | | | 13.02 | 5.77 | +0.96 (0.86) |

Contributions are percentage points of 2022–2025 growth. The implicate
standard deviation pairs implicates by index across the two windows.

CPI-U rose 10.01% over the same span (`cpi_annual.json`, 292.655 to
321.943). BLS's thresholds rose 10.6–12.1 points more than CPI-U. Without
the stage the replication reproduces 85% of that excess for renters, 96%
for owners with mortgages and 83% for owners without; with the stage,
81%, 97% and 92%.

In-kind benefits change the replication's 2022–2025 growth by −0.6
points for renters, +0.1 for owners with mortgages and +1.0 for owners
without mortgages. Each lies within about one between-implicate standard
deviation of zero, before any sampling uncertainty. The lift itself
moved little: from 3.60% to 3.10% for renters, 2.70% to 2.76% for owners
with mortgages and 1.61% to 2.43% for owners without mortgages. Mean
imputed amounts rose 21% in threshold-year dollars ($957 to $1,156), in
line with the 19–21% growth of the out-of-pocket thresholds. Real
out-of-pocket spending in the CE, not in-kind benefits, carries the
replication's growth beyond prices, and the stage leaves the renter
shortfall against BLS's growth unexplained (−1.8 points without the
stage, −2.4 with it). The package's composite CPI assigns about one point
less to prices than BLS's FCSUti index, and the decomposition moves that
point to real spending. The decomposition attributes fixed thresholds;
the last results section reruns the replication with BLS's index as the
deflator, which changes the thresholds themselves.

### Year over year

In-kind contribution to each year's growth, in percentage points, with
the between-implicate standard deviation:

| Years | Renter | Owner with mortgage | Owner without mortgage |
|---|---:|---:|---:|
| 2019–2020 | −0.09 (0.13) | +0.13 (0.11) | −0.11 (0.21) |
| 2020–2021 | +0.43 (0.11) | −0.29 (0.08) | −1.51 (0.21) |
| 2021–2022 | +0.48 (0.14) | +0.32 (0.21) | −0.71 (0.53) |
| 2022–2023 | −1.16 (0.13) | +0.53 (0.13) | +0.70 (1.23) |
| 2023–2024 | +0.62 (0.26) | −0.15 (0.24) | −1.26 (1.30) |
| 2024–2025 | −0.01 (0.17) | −0.30 (0.13) | +1.37 (0.78) |

The in-kind term runs from −1.5 to +1.4 points a year. Owners without
mortgages swing most and carry the largest implicate spread: they make
up fewer than one in ten units in the estimation band (136 of 1,550 in
the 2025 out-of-pocket band), so a few units reorder their mean. Each
window shares four of its five reference years with the next, and
sampling uncertainty remains unestimated, so single-year movements of
this size deserve caution.

### Deflating with BLS's FCSUti index

The replication carries each unit's spending to threshold-year dollars
with a composite of five CPI-U series (food, apparel, shelter, fuels and
utilities, and telephone services), weighted by the window's CE spending
and applied by collection year. BLS deflates with its FCSUti index, which
it builds from CPI basic item-area indexes. That index also prices
internet service, and its 2025 average imputes October, which BLS did not
collect ([BLS 2025 thresholds](https://www.bls.gov/pir/spm/spm_thresholds_2025.htm)).
A sensitivity run replaces every component series with BLS's published
FCSUti levels ([BLS table](https://www.bls.gov/pir/spm/spm_chart_2025data.htm)),
so each unit's price factor becomes `I(T) / I(c)` for collection year
`c`; the script checks that factor for every collection year.

2022–2025 growth:

| Tenure | BLS corrected | Package CPI, without stage | Package CPI, with stage | FCSUti, without stage | FCSUti, with stage |
|---|---:|---:|---:|---:|---:|
| Renter | +22.15% | +20.37% | +19.78% | +21.48% | +20.94% |
| Owner with mortgage | +21.61% | +21.15% | +21.22% | +22.08% | +22.13% |
| Owner without mortgage | +20.63% | +18.79% | +19.75% | +20.81% | +21.64% |

BLS's index adds 1.1 points of 2022–2025 growth for renters, 0.9 for
owners with mortgages and 2.0 for owners without mortgages: in each
tenure, more than the in-kind stage moves it. Without the stage, the
replication's growth then lands within 0.7 points of BLS's for every
tenure (−0.67, +0.47 and +0.18 points) and reproduces 95%, 104% and 102%
of BLS's growth above CPI-U. With the stage, renters fall 1.21 points
short and owners without mortgages run 1.01 points ahead.

Signed gap from BLS's corrected thresholds in percent with FCSUti
deflation, without → with the stage:

| Target | Renter | Owner with mortgage | Owner without mortgage |
|---|---:|---:|---:|
| 2019 | −0.76 → +2.08 | −1.35 → +1.20 | −0.54 → +3.10 |
| 2020 | −1.16 → +1.53 | −1.31 → +1.37 | +0.23 → +3.81 |
| 2021 | −1.34 → +1.72 | −1.55 → +0.84 | +0.48 → +2.91 |
| 2022 | −1.63 → +1.84 | −1.67 → +0.97 | +1.00 → +2.91 |
| 2023 | −1.10 → +1.47 | −2.10 → +1.05 | +0.65 → +2.58 |
| 2024 | −0.96 → +2.05 | −1.99 → +1.09 | +1.29 → +2.57 |
| 2025 | −2.16 → +0.83 | −1.29 → +1.40 | +1.15 → +3.77 |

Out-of-pocket levels move by −0.65% to +1.04% against the package-CPI
run, and the stage still carries every tenure above BLS in every year.
The run shows how much the deflator matters, not how BLS deflates: BLS's
index prices internet service, which the replication's spending omits,
and the run keeps the replication's annual price factors by collection
year.

## Limitations

- BLS has not published its imputation code or covariates; the models
  here follow its method description.
- The rental model is a log-normal Tobit on CE unit characteristics and
  takes reported rents as exact.
- School lunch donor values for reference years 2014–2017 come from the
  USDA formula; later years use Census `SPM_SCHLUNCH` values.
- The imputation assigns school lunch only to households it imputes as
  receiving free, reduced-price or universal-free lunch. Census also
  values paid lunches and, in some years, P-EBT or Summer EBT for
  households without free or reduced-price lunch.
- WIC uses USDA's national fiscal-year average food cost; Census has used
  state averages since its revised 2019 estimates.
- All participation models share one covariate set across programs and
  years, and the CE and CPS income concepts differ.
- The replication still omits home internet spending.
- The runs estimate imputation uncertainty (implicate spread) but not
  sampling uncertainty.

## Forecast windows: a proposed design

The stage covers observed windows only. The
[rolling forecasts](rolling-forecasts.md) project a future window by
copying same-season donor quarters, keeping each donor's `NEWID`, and
scaling monetary columns, then anchor national levels as
`published_2025 × replication_T / replication_2025`. A follow-up could
carry the stage into those windows:

1. Impute on the projected window with the latest CPS ASEC donors. Draws
   key on `NEWID`, which projected copies keep, so a projected unit
   reuses its donor's random draws.
2. Revalue projected quarters with each target year's program rules:
   school lunch with the reimbursement rates USDA publishes each July
   (adjusted with the CPI-U Food Away From Home series, per the Federal
   Register notices); WIC stays zero; broadband becomes zero from
   reference year 2025, since the ACP ended in June 2024 (Census SPM
   technical documentation); LIHEAP and rental assistance scale with the
   window's price factor.
3. Anchor with the stage on, `published_2025 × R_in_kind(T) /
   R_in_kind(2025)`, and keep any direct forecast of the in-kind ratio as
   a cross-check only.

Nothing in the canonical forecast uses the stage today.

## Files

- `spm_calculator/ce_inkind.py`: the imputation.
- `spm_calculator/ce_inkind_stage.py`: the stage that adds a table of
  amounts to the CE frame and re-estimates thresholds.
- `spm_calculator/ce_decomposition.py`: the growth decomposition and
  BLS's published FCSUti levels, 2002–2025.
- `spm_calculator/cps_asec.py`: CPS ASEC household donors.
- `spm_calculator/data/inkind/`: USDA lunch rates and donated-food values,
  WIC food costs and EBT dates, official poverty thresholds, and the
  Census lunch values the differential test checks, each with its source.
- `scripts/build_inkind_parameters.py`: rebuilds the poverty-threshold
  and observed-lunch files.
- `scripts/replicate_ce_inkind.py` and
  `spm_calculator/data/current/ce_inkind_replication_2019_2025.json`: the
  2019–2025 run and its receipt, with code, data and parameter hashes.
