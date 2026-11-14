# CE in-kind benefit imputation

BLS adds five imputed in-kind benefits to each consumer unit's out-of-pocket
FCSUti before it estimates SPM thresholds: school lunch (NSLP), WIC, LIHEAP,
broadband subsidies and rental assistance. It leaves SNAP out because it
assumes households spend SNAP's EBT benefits like cash, so reported food
spending already includes them ([BLS SPM thresholds
page](https://www.bls.gov/pir/spmhome.htm)). BLS describes its current
imputation models briefly on that page, and [Garner and Gudrais
(2018)](https://www.bls.gov/osmr/research-papers/2018/pdf/ec180100.pdf)
document an earlier version in more detail, but BLS has not published its
code. We implement the page's description as an optional stage of the
package's [CE replication](current-ce-replication.md), which omits all five
benefits by default, and rerun the 2019–2025 thresholds with and without
them to measure how much the benefits explain of the replication's gap to
BLS's corrected thresholds and of threshold growth.

- We estimate that imputed benefits raise the replication's thresholds by
  0.9–3.8% and carry them above BLS's corrected levels for every tenure in
  every year from 2019 to 2025. Our shelter term more than offsets the omitted
  home internet term, and our rental assistance adds to the renter gap. BLS's
  papers define shelter, utilities and food more narrowly than the replication
  does, and under those definitions the replication with the stage lands
  between 1.7% below and 1.5% above BLS.
- We estimate that they change 2022–2025 threshold growth by −0.6 to +1.0
  points, each within one standard error of zero with sampling and
  imputation uncertainty combined.
- Deflating with BLS's FCSUti index instead of the package's composite CPI
  adds 0.9–2.0 points of 2022–2025 growth, more in every tenure than the
  stage moves it, and brings the replication without the stage within 0.7
  points of BLS's growth for every tenure.
- We compute BLS's in-band dollars from its published shares. Our imputed
  total exceeds BLS's through 2024 and trails it in 2025. From 2022 to 2025,
  BLS's imputed benefits rise \$401 and ours \$151, and removing imputed terms
  from both narrows the renter growth shortfall from −2.41 to −0.97 points.

Sections: [method](#method), [results](#results), [comparison with BLS
components](#comparison-with-bls-components), [sampling
uncertainty](#sampling-uncertainty), [limitations](#limitations) and [how to
run it](#run-it).

## Method

BLS has not published its imputation code. Its methods page describes the
current models briefly, and [Garner and Gudrais
(2018)](https://www.bls.gov/osmr/research-papers/2018/pdf/ec180100.pdf)
document an earlier version: its participation covariates, five pooled years
of CPS ASEC households with state fixed effects, and a two-step rent
regression. The models here follow the methods page, the Census SPM
technical documentation that BLS cites for benefit values, and USDA program
data, with covariates that both surveys measure. Each threshold year T uses
CE collection quarters (T−5)Q2 through TQ1. A collection quarter (y, q)
covers reference year y when q ≥ 2 and y − 1 when q = 1, and the imputation
for reference year r draws donors from the CPS ASEC of survey year r + 1.

| Component | Participation | Value | Enters |
|---|---|---|---|
| School lunch (NSLP) | Logit on CPS households with a member aged 5–18 (`HFLUNCH`). The CE universe applies only the age rule, as BLS does. | Hot deck from participating CPS households in the same state, SNAP, below-150%-of-poverty and child-count cell (when a cell has fewer than five donors or the CE withholds the unit's state, widening from state to region, then across numbers of children, then across regions, and last to all donors), scaled to the CE unit's children aged 5–18. Donor values: Census's `SPM_SCHLUNCH` for reference years 2018 onward; for earlier years, the traditional formula (USDA reimbursement plus donated-food value per lunch, weighted 5/9 spring and 4/9 fall school year, times 179 days, for each child receiving lunch; free below 150% of the official poverty line, otherwise free or reduced with equal probability). | FCSUti |
| WIC | Logit on CPS households in the WIC universe | Census's participant rule (all children under 5, plus the mother of a child aged 0–1 when the unit includes a woman 15 or older, otherwise one pregnant woman) × 12 × USDA's national fiscal-year average monthly food cost. Zero from reference year 2020, and earlier where the state finished WIC EBT before the middle of the reference period. | FCSUti |
| LIHEAP | Logit on all CPS households | Predictive mean matching on household-reported `HENGVAL` | FCSUti and SU |
| Broadband (EBB, ACP) | Logit on all CPS households, reference years 2022 onward | Predictive mean matching on Census's assigned `SPM_BBSUBVAL` | FCSUti |
| Rental assistance | CE renters reporting `GOVTCOST` or `PUBLHOUS` in the rent file | Weighted Tobit of log monthly rent paid on unit characteristics, with assisted units censored from above at their rent paid. Benefit = 12 × (imputed market rent − rent paid). | FCSUti and SU |

Participation models share one covariate set that both surveys measure:
income relative to the official poverty threshold, SNAP, public
assistance, SSI and housing-assistance receipt, tenure, household size,
counts of children under 5, children aged 5–18, members 65 and over and
earners, and the reference person's age, sex, race, Hispanic origin and
education. Each model uses state indicators where the CE identifies the
state, region indicators where it identifies only the region, and neither
otherwise. Garner and Gudrais (2018) also use marital status, employment
status, disability, single parenthood, Medicaid and urban residence, which
these models omit. A CE unit receives SNAP when it reports an amount
(`JFS_AMT`), CE completes one (`JFS_AMTM`) or it reports months of
receipt (`FS_MTHI`). Census's school lunch values carry its COVID-era
methods for virtual schooling and P-EBT (Shrider 2021, 2022, 2023), which
BLS also says it follows, and its later universal-free-meal and Summer
EBT rules.

Predictive mean matching fits a weighted regression of log amount on
CPS recipients, then gives each imputed CE recipient the amount of one
of the five CPS recipients nearest to it in predicted value, chosen by
the unit's hashed draw. A unit beyond either end of the donor range
draws from the five end donors, never from repeated copies of one.

When no CPS donor in a program's universe participates in a reference
year, or every one does, the logit has no finite estimate. The stage then
gives every CE unit in the universe that constant outcome and records it
in the diagnostics. Broadband reaches the first case once Census's values
fall to zero after the ACP ended.

BLS adds broadband subsidies from the 2023 thresholds, with underlying data
from 2022 ([thresholds
workbook](https://www.bls.gov/pir/spm/spm_thresholds.xlsx), footnote 3), so
we impute them from reference year 2022. Census values them from reference
year 2021, when the Emergency Broadband Benefit began.

The WIC universe follows BLS: a woman aged 15–45, or a child under 5 with
a woman aged 15 or older. From the 2025 thresholds BLS drops the woman
requirement for units with children under 5, so `for_target` applies the
older rule to earlier targets. BLS adds WIC only "if a state has not fully
implemented WIC via electronic benefit transfer"
([SPM thresholds methods](https://www.bls.gov/pir/spmhome.htm)). The
Healthy, Hunger-Free Kids Act of 2010 required each WIC state agency to
implement EBT statewide by October 1, 2020, unless the Secretary of
Agriculture granted an exemption ([42 U.S.C.
1786(h)(12)(B)](https://www.law.cornell.edu/uscode/text/42/1786)). For
reference years before 2020, we compare each state's statewide date, from
FNS's December 2022 WIC EBT status report (in `data/inkind/`), with the
middle of the unit's reference period. Where the CE withholds the state, a
unit counts as finished with probability equal to the weighted share of
finished units in its region and collection quarter. From reference year
2020, the year of the statutory deadline, we add no WIC in any state. The
cutoff also drops WIC where the middle of the reference period falls
before the deadline, including in the six states that finished during
2020 before October 1, from Hawaii in June to Illinois in September. FNS
dates six other states and DC after the deadline, from Utah in November
2020 to Georgia in October 2022. In both groups, a strict state-by-state
reading of BLS's rule would still add WIC where our cutoff adds none.
With each state's own date in every year, we estimate that mean WIC per
unit rises by \$1.94–\$3.21 for the 2021–2025 targets. Those thresholds move
by −\$20 to +\$40 (−0.06% to +0.12%) as the added WIC reorders units in the
band, and 2022–2025 growth changes by 0.03 points or less. For its 2025
thresholds, BLS counts \$1.80 of WIC per unit in the band.

BLS fits a limited dependent variable model that treats assisted renters'
rents as censored from above, and values the benefit as imputed market rent
less rent paid. Garner and Gudrais (2018) document an earlier two-step
model: a logistic regression for paying market rent, then, among the renters
who do, a regression of log rent on building characteristics and the first
step's Mills ratio, with state and year effects; they predict a market rent
for each assisted unit. The rental model here fits renters per reference
year: unassisted units with rent of at least \$50 a month enter as observed,
and assisted units that report rent enter as censored at their rent paid. Rent paid is the rent file's three-month
rent (`QRT3MCMX`) summed over the unit's records and divided by three.
That sum equals the unit's rent-of-dwelling expenditure, UCC 210110,
which a test checks on cached CE data; the FMLI summary of rented
dwellings (`RENDWEPQ + RENDWECQ`) also counts maintenance, insurance and
other costs. Covariates cover bedrooms, bathrooms,
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
can still lower a tenure's threshold: added benefits reorder units and
change which of them land in the 47th–53rd percentile band. In 2024,
rental assistance alone lowers the threshold for owners without mortgages
by 0.67%, and school lunch alone lowers it by 0.57%.

## Invariants

1. Imputed amounts are finite and nonnegative for every unit and
   component.
2. The stage never lowers any unit's FCSUti or SU.
3. An all-zero in-kind table reproduces the out-of-pocket thresholds,
   estimation diagnostics and normalized expenditures exactly. The default
   replication runs no in-kind code.
4. Imputation repeats exactly and does not depend on row order.
5. Units outside a component's universe get zero: school lunch needs a
   member aged 5–18, WIC needs the universe, a reference year before 2020
   and a state without complete EBT, broadband needs reference year 2022 or
   later, and rental assistance needs an assisted renter.
6. Growth factors exactly into price × real out-of-pocket × in-kind, and
   the additive contributions sum to total growth.
7. Every predictive mean matching pool holds min(k, n) distinct donors,
   the k nearest to the target by predicted value.
8. In-band component means reproduce every threshold, with and without the
   stage, and a mean over implicates reproduces the mean threshold.
9. BLS's published shares, thresholds and tenure distribution satisfy
   both identities in the [comparison with BLS components](#comparison-with-bls-components)
   in every year from 2019 to 2025.
10. Each threshold term's part of the gap to BLS sums to the whole gap, and
    the imputed and other terms' shares of growth beyond inflation sum to
    one.
11. Applying BLS's written definitions lowers each unit's FCSUti by exactly
    the amounts they remove, and a second application changes nothing.
12. Replicate variances never fall below zero, vanish when every replicate
    equals the full sample, and stay the same when the estimate and its
    replicates shift by a common amount or the replicates change order.
13. Rubin's total variance never falls below the mean within-implicate
    variance or below (1 + 1/M) times the between-implicate variance, and the
    degrees of freedom never exceed the complete-data value.
14. With every replicate weight set to the full-sample weight, each replicate
    reproduces the full-sample thresholds exactly.
15. Band means reproduce every replicate's thresholds, with and without the
    stage.
16. Replicate estimates repeat exactly.

`tests/test_ce_bls_shares.py` checks invariants 8–11, with Hypothesis
property tests on synthetic data and direct checks on BLS's workbook, and
fails when the comparison's receipt no longer matches its code or a table
below no longer matches the receipt. On every real CE window, the comparison
script stops unless in-band component means reproduce every threshold, with and
without the stage. It also deflates every component with BLS's FCSUti index and
stops unless each unit's shelter, utilities and food fall by the amounts the
definitions remove, to within a millionth of a dollar. Only the synthetic tests
apply the definitions twice.

`tests/test_ce_inkind.py` checks invariants 1–7 on synthetic CE and CPS data:
Hypothesis property tests cover invariants 1, 2, 3, 6 and 7 (the last
against brute force, with tied predictions and targets beyond the donor
range), and fixture tests cover 4 and 5. It also checks rent paid against
UCC 210110 in the second quarters of 2015, 2019 and 2024 when those CE
bundles are cached, compares the USDA lunch formula with
the values Census assigned in 2018 and 2019 (the formula gives
\$626.35/\$554.75 against Census's \$627/\$555, and \$642.71/\$571.11 against
\$643/\$571), checks that the logit and Tobit recover known parameters,
and fails when the committed receipt no longer matches the code that
produced it.

`tests/test_ce_replicates.py` checks invariants 12–15 with Hypothesis
property tests on synthetic data and invariant 16 on a fixture. It holds each
replicate to the stage's public functions run on the reweighted sample and
Rubin's rules to a separate implementation. It recomputes every standard error
in the [sampling uncertainty](#sampling-uncertainty) receipt from the
replicates the receipt stores, and it fails when the receipt no longer matches
its code or the page's tables no longer match the receipt.

## Results

All figures come from the committed receipt, five implicates, with CPI
pinned to the package's `cpi_annual.json` unless a section says
otherwise. We estimate thresholds on consumer units with children.

### Imputed amounts

Mean amount per consumer unit in the estimation sample, in threshold-year
dollars:

| Target | School lunch | WIC | LIHEAP | Broadband | Rental assistance | Total | Share with any |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2019 | 321 | 52 | 18 | 0 | 447 | 838 | 34.0% |
| 2020 | 344 | 44 | 18 | 0 | 444 | 849 | 34.7% |
| 2021 | 335 | 32 | 18 | 0 | 454 | 839 | 33.1% |
| 2022 | 425 | 23 | 22 | 0 | 486 | 955 | 36.3% |
| 2023 | 508 | 13 | 26 | 3 | 480 | 1,029 | 38.5% |
| 2024 | 551 | 6 | 26 | 7 | 504 | 1,094 | 39.8% |
| 2025 | 586 | 0 | 26 | 8 | 528 | 1,149 | 41.0% |

School lunch and rental assistance supply over 90% of the total in every
year. School lunch grows the most, from \$321 to \$586 a unit. Among CPS
households with school-age children, reported participation rises from
33% in reference year 2014 to 54% in 2021, then falls back to 49% in
2024, while the mean donor value per participating household rises from
\$989 (2014, USDA formula) to \$1,388 (2024, Census values).

The CE imputation tracks its CPS donors. Weighted participation, CE
imputed against CPS donors, by reference year:

| Component | 2014 | 2018 | 2021 | 2024 |
|---|---|---|---|---|
| School lunch (households with a member 5–18) | 34.3% / 33.2% | 38.3% / 37.2% | 54.8% / 53.7% | 47.9% / 48.6% |
| WIC (CPS: WIC universe; CE: also units with a child under 5) | 7.5% / 7.5% | 6.1% / 5.5% | 5.0% / 4.8% | 5.6% / 5.4% |
| LIHEAP (all) | 3.6% / 3.5% | 3.5% / 3.2% | 3.4% / 3.2% | 3.6% / 3.3% |
| Broadband (all) | — | — | — | 2.7% / 2.4% |

The WIC row counts every unit the model assigns to WIC, including units that
receive none because their interviews reference 2020 or later or their state
had finished EBT.

Rental assistance comes from the CE itself: 12.7% of CE renters report
assistance in 2014 and 14.0% in 2024, with mean annual benefits of \$7,608
and \$12,210 per assisted unit.

### Levels: gap to BLS's corrected thresholds

Signed gap from BLS's corrected thresholds in percent, without → with the
stage:

| Target | Renter | Owner with mortgage | Owner without mortgage |
|---|---:|---:|---:|
| 2019 | −1.12 → +1.73 | −1.67 → +0.94 | −1.00 → +2.75 |
| 2020 | −1.45 → +1.28 | −1.69 → +1.04 | −0.24 → +3.53 |
| 2021 | −1.36 → +1.78 | −1.55 → +0.88 | +0.78 → +2.98 |
| 2022 | −1.33 → +2.27 | −1.41 → +1.24 | +1.67 → +3.14 |
| 2023 | −1.07 → +1.50 | −2.05 → +1.04 | +0.72 → +2.87 |
| 2024 | −1.40 → +1.71 | −2.25 → +0.71 | +1.14 → +2.07 |
| 2025 | −2.77 → +0.25 | −1.79 → +0.90 | +0.11 → +2.45 |

The without column matches the [September 8 replication](current-ce-replication.md)
exactly. In-kind lift (percent of the out-of-pocket threshold), with the
between-implicate standard deviation of the threshold with the stage, in
percent of that threshold:

| Target | Renter | Owner with mortgage | Owner without mortgage |
|---|---:|---:|---:|
| 2019 | 2.88 (0.22) | 2.65 (0.22) | 3.79 (0.23) |
| 2020 | 2.77 (0.26) | 2.78 (0.19) | 3.77 (0.34) |
| 2021 | 3.18 (0.16) | 2.47 (0.20) | 2.19 (0.33) |
| 2022 | 3.64 (0.18) | 2.69 (0.19) | 1.45 (0.33) |
| 2023 | 2.59 (0.09) | 3.16 (0.05) | 2.13 (0.90) |
| 2024 | 3.15 (0.22) | 3.02 (0.19) | 0.93 (0.77) |
| 2025 | 3.10 (0.37) | 2.74 (0.13) | 2.34 (0.90) |

Share of the gap the stage closes, `(with − without) / (BLS − without)`.
Values above 1 overshoot; negative values mean the replication already
exceeded BLS and the stage moves it further above. A dash marks gaps
under 0.5%, where the ratio means little.

| Target | Renter | Owner with mortgage | Owner without mortgage |
|---|---:|---:|---:|
| 2019 | 2.54 | 1.57 | 3.75 |
| 2020 | 1.88 | 1.62 | — |
| 2021 | 2.30 | 1.57 | −2.82 |
| 2022 | 2.70 | 1.88 | −0.89 |
| 2023 | 2.40 | 1.51 | −2.97 |
| 2024 | 2.22 | 1.31 | −0.82 |
| 2025 | 1.09 | 1.51 | — |

Without the stage, the replication runs 1.07–2.77% below BLS for renters
and 1.41–2.25% below for owners with mortgages in every year. The stage
lifts thresholds by 2.47–3.64% for those two groups, so both land above
BLS in every year: renters by 0.25–2.27% and owners with mortgages by
0.71–1.24%. Owners without mortgages already sit above BLS in five of
seven years, and the stage moves them to 2.07–3.53% above.

BLS's FCSUti also includes home internet spending, which the replication
omits because the FMLI file has no dedicated internet summary, so the
out-of-pocket gap mixes both omissions. The replication's shelter and utilities
hold more than BLS's papers describe, and its other approximations (annual CPI,
the food allocation, the percentile convention and sample policies) move levels
too. In the [comparison with BLS components](#comparison-with-bls-components),
we split the gap by term and rerun the replication under BLS's written
definitions.

Component lifts, each component alone, in percent of the out-of-pocket
threshold:

| Component | 2022 renter | 2022 with mortgage | 2022 without mortgage | 2025 renter | 2025 with mortgage | 2025 without mortgage |
|---|---:|---:|---:|---:|---:|---:|
| School lunch | +1.28 | +1.40 | +0.12 | +1.37 | +1.30 | +1.93 |
| WIC | +0.10 | +0.05 | −0.25 | +0.00 | +0.00 | +0.00 |
| LIHEAP | +0.12 | +0.03 | −0.08 | +0.02 | +0.04 | +0.25 |
| Broadband | +0.00 | +0.00 | +0.00 | −0.04 | −0.00 | +0.39 |
| Rental assistance | +2.48 | +1.30 | +0.71 | +1.97 | +1.19 | +1.23 |

For renters and owners with mortgages, school lunch and rental
assistance alone add 91–108% of the stage's lift in both years. The
components interact through band composition, so they do not sum to the
total: for owners without mortgages, the two add 57% of the lift in 2022
and 135% in 2025.

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
| Renter | +22.15% | +20.37% | +19.74% | 14.19 | 6.18 | −0.63 (0.60) |
| Owner with mortgage | +21.61% | +21.15% | +21.21% | 14.19 | 6.96 | +0.06 (0.38) |
| Owner without mortgage | +20.63% | +18.79% | +19.82% | 14.19 | 4.59 | +1.04 (1.08) |
| Package composite CPI | | | | | | |
| Renter | | | | 13.25 | 7.12 | −0.63 (0.60) |
| Owner with mortgage | | | | 13.12 | 8.03 | +0.06 (0.38) |
| Owner without mortgage | | | | 13.02 | 5.77 | +1.04 (1.08) |

Contributions are percentage points of 2022–2025 growth. The implicate
standard deviation pairs implicates by index across the two windows.

CPI-U rose 10.01% over the same span (`cpi_annual.json`, 292.655 to
321.943). BLS's thresholds rose 10.6–12.1 points more than CPI-U. Without
the stage the replication reproduces 85% of that excess for renters, 96%
for owners with mortgages and 83% for owners without; with the stage,
80%, 97% and 92%.

In-kind benefits change the replication's 2022–2025 growth by −0.6
points for renters, +0.1 for owners with mortgages and +1.0 for owners
without mortgages. Each lies within one standard error of zero with sampling
and imputation uncertainty combined
([standard errors of growth](#growth-from-2022-to-2025)). The lift itself
moved little: from 3.64% to 3.10% for renters, 2.69% to 2.74% for owners
with mortgages and 1.45% to 2.34% for owners without mortgages. Mean
imputed amounts across the estimation sample rose 20% in threshold-year
dollars (\$955 to \$1,149), in line with the 19–21% growth of the
out-of-pocket thresholds. Within the band that sets the thresholds, they
rose 15%. Real out-of-pocket spending in the CE, not in-kind benefits,
carries the replication's growth beyond prices, and the stage widens the
renter shortfall against BLS's growth from −1.8 points to −2.4. BLS's
imputed amounts rise faster than ours, and while we hold each band fixed,
that difference accounts for 1.43 of those 2.41 points
([comparison with BLS components](#comparison-with-bls-components)).
The package's composite CPI rises about one point less than BLS's FCSUti
index, so with the package CPI that point moves from prices to real spending.
We hold thresholds fixed for this decomposition; when we rerun the replication
with BLS's index as the deflator, the thresholds themselves change.

### Year over year

In-kind contribution to each year's growth, in percentage points, with
the between-implicate standard deviation:

| Years | Renter | Owner with mortgage | Owner without mortgage |
|---|---:|---:|---:|
| 2019–2020 | −0.11 (0.20) | +0.13 (0.11) | −0.01 (0.34) |
| 2020–2021 | +0.42 (0.12) | −0.32 (0.12) | −1.59 (0.17) |
| 2021–2022 | +0.49 (0.13) | +0.24 (0.17) | −0.79 (0.65) |
| 2022–2023 | −1.11 (0.25) | +0.49 (0.22) | +0.71 (0.97) |
| 2023–2024 | +0.57 (0.18) | −0.14 (0.21) | −1.28 (1.32) |
| 2024–2025 | −0.05 (0.17) | −0.29 (0.12) | +1.45 (0.73) |

The in-kind term runs from −1.6 to +1.4 points a year. Owners without
mortgages swing most and carry the largest implicate spread: they make
up fewer than one in ten units in the estimation band (136 of 1,550 in
the 2025 out-of-pocket band), so a few units reorder their mean. Each
window shares four of its five reference years with the next, and none of
these changes reaches two standard errors with sampling and imputation
uncertainty combined ([standard errors by year](#yearly-growth)).

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
| Renter | +22.15% | +20.37% | +19.74% | +21.48% | +20.88% |
| Owner with mortgage | +21.61% | +21.15% | +21.21% | +22.08% | +22.10% |
| Owner without mortgage | +20.63% | +18.79% | +19.82% | +20.81% | +21.76% |

With or without the stage, BLS's index adds 1.1 points of 2022–2025 growth
for renters, 0.9 for owners with mortgages and 1.9–2.0 for owners without
mortgages, more in each tenure than the stage moves it. Without the stage, the
replication's growth then lands within 0.7 points of BLS's for every
tenure (−0.67, +0.47 and +0.18 points) and reproduces 95%, 104% and 102%
of BLS's growth above CPI-U. With the stage, renters fall 1.26 points
short and owners without mortgages run 1.13 points ahead.

The stage's change in 2022–2025 growth with each deflator, in percentage
points, with the between-implicate standard deviation:

| Tenure | Package CPI | FCSUti index |
|---|---:|---:|
| Renter | −0.63 (0.60) | −0.60 (0.50) |
| Owner with mortgage | +0.06 (0.38) | +0.01 (0.46) |
| Owner without mortgage | +1.04 (1.08) | +0.95 (1.00) |

With BLS's index, the renter change reaches 1.2 between-implicate standard
deviations, and the other two stay within one. With sampling and imputation
uncertainty combined, all six changes lie within one standard error of zero
([standard errors of growth](#growth-from-2022-to-2025)).

Signed gap from BLS's corrected thresholds in percent with FCSUti
deflation, without → with the stage:

| Target | Renter | Owner with mortgage | Owner without mortgage |
|---|---:|---:|---:|
| 2019 | −0.76 → +2.16 | −1.35 → +1.24 | −0.54 → +3.21 |
| 2020 | −1.16 → +1.63 | −1.31 → +1.41 | +0.23 → +3.71 |
| 2021 | −1.34 → +1.76 | −1.55 → +0.92 | +0.48 → +2.83 |
| 2022 | −1.63 → +1.88 | −1.67 → +0.96 | +1.00 → +2.80 |
| 2023 | −1.10 → +1.52 | −2.10 → +1.01 | +0.65 → +2.50 |
| 2024 | −0.96 → +2.05 | −1.99 → +1.08 | +1.29 → +2.51 |
| 2025 | −2.16 → +0.82 | −1.29 → +1.36 | +1.15 → +3.76 |

Out-of-pocket levels move by −0.65% to +1.04% against the package-CPI
run, and the stage still carries every tenure above BLS in every year.
The run shows how much the deflator matters, not how BLS deflates: BLS's
index prices internet service, which the replication's spending omits,
and the run keeps the replication's annual price factors by collection
year.

## Comparison with BLS components

BLS computes each component's share of each threshold from the components'
values within the percentile band and publishes the shares
([shares workbook](https://www.bls.gov/pir/spm/spm_shares.xlsx)). It also
publishes each tenure's weighted share of the consumer units with children in
that band
([thresholds workbook](https://www.bls.gov/pir/spm/spm_thresholds.xlsx),
footnote 3). From those two files we compute BLS's in-band dollars. With
`F = C + SU`, where `C` sums the components every tenure shares, a threshold
`T_h = 0.82 × (1.2 × F − SU + SU_h)` rearranges to:

```text
T_h / 0.82 = C + SU_h + 0.2 × F
F          = C + Σ_h P_h × SU_h
```

A share times `T_h / 0.82` gives a component's dollars, and BLS's "Other"
share gives `0.2 × F`. With `P_h` as the tenure's share of the band, BLS's
published values satisfy both identities within \$0.00001 in every year from
2019 to 2025. We compute the same means for the replication's band with
`spm_calculator/ce_bls_shares.py`, and they reproduce every threshold.

We split each threshold into terms in two ways, and both sum to the
threshold. For the accounting labelled Other spread, we give each component
its part of the 1.2 multiplier: `0.82 × 1.2 × c` for a component every tenure
shares, and `0.82 × (c_h + 0.2 × c)` for shelter, utilities, LIHEAP and rental
assistance. Each term then gives what the threshold would lose without its
component if the band stayed the same. For Other separate, we keep
`0.82 × 0.2 × F` as its own term, as BLS's workbook does in its "Other Share"
row, and enter each component at `0.82 × c`, or at `0.82 × c_h` for shelter,
utilities, their benefits and broadband. Home internet takes the rest of the
total it shares with broadband. Each separate term over its threshold then gives the
component's share as BLS publishes it, and BLS's terms reproduce every
published share within one billionth in every year from 2019 to 2025.
Removing imputed terms from growth also removes their parts of `0.2 × F`, so
the figures that remove those terms use Other spread.

All figures in this section come from
`ce_inkind_bls_components_2019_2025.json`, in threshold-year dollars for two
adults and two children. Unless a table says otherwise, ours include the stage
and use the package CPI.

### Imputed amounts in the band

Mean per consumer unit in the 47th–53rd percentile band, our estimate / BLS's.
Rental assistance averages over all renters in the band, assisted or not.

| Target | All imputed benefits | Rental assistance per renter | School lunch |
|---|---:|---:|---:|
| 2019 | \$889 / \$705 | \$1,113 / \$630 | \$318 / \$371 |
| 2020 | \$881 / \$742 | \$1,094 / \$633 | \$331 / \$402 |
| 2021 | \$913 / \$764 | \$1,238 / \$712 | \$328 / \$407 |
| 2022 | \$1,024 / \$855 | \$1,335 / \$738 | \$425 / \$500 |
| 2023 | \$1,045 / \$927 | \$1,314 / \$772 | \$481 / \$596 |
| 2024 | \$1,067 / \$1,049 | \$1,285 / \$940 | \$522 / \$664 |
| 2025 | \$1,175 / \$1,257 | \$1,464 / \$1,243 | \$571 / \$742 |

We estimate that our rental assistance per renter exceeds BLS's by 18–81% in
every year, and that our school lunch trails BLS's by 14–23%. Our estimated
total exceeds BLS's by 13–26% through 2023 and by 2% in 2024, then trails it by
6% in 2025. Between-implicate standard deviations reach \$188 for rental
assistance per renter and \$18 for school lunch.

Each tenure's share of the band in percent, ours / BLS's:

| Target | Renter | Owner with mortgage | Owner without mortgage |
|---|---:|---:|---:|
| 2019 | 44.9 / 43.4 | 47.7 / 47.4 | 7.4 / 9.2 |
| 2020 | 44.4 / 44.3 | 47.9 / 46.8 | 7.7 / 8.9 |
| 2021 | 43.1 / 43.1 | 48.9 / 48.1 | 8.0 / 8.8 |
| 2022 | 41.5 / 41.5 | 50.4 / 50.3 | 8.1 / 8.1 |
| 2023 | 39.3 / 38.1 | 52.8 / 52.0 | 7.8 / 9.9 |
| 2024 | 39.3 / 37.2 | 52.7 / 52.7 | 8.0 / 10.0 |
| 2025 | 38.7 / 38.7 | 53.7 / 51.0 | 7.6 / 10.2 |

Our band's share of owners without mortgages trails BLS's in every year, by up
to 2.6 points.

### The level gap, term by term

Each term's part of the gap in percentage points of BLS's threshold, lowest to
highest over 2019–2025, with Other spread:

| Term | Renter | Owner with mortgage | Owner without mortgage |
|---|---:|---:|---:|
| Imputed benefits | +0.11 to +1.36 | −0.37 to −0.03 | −0.56 to −0.04 |
| Shelter | +2.35 to +3.99 | +2.82 to +3.67 | +4.92 to +6.85 |
| Home internet | −2.14 to −1.86 | −2.14 to −1.85 | −2.55 to −2.20 |
| Utilities | −0.33 to +0.33 | −0.00 to +0.43 | −0.80 to +0.73 |
| Food | −0.05 to +0.46 | −0.05 to +0.46 | −0.05 to +0.55 |
| Clothing | −0.81 to −0.24 | −0.81 to −0.24 | −0.96 to −0.29 |
| Telephone | −0.09 to +0.19 | −0.09 to +0.19 | −0.11 to +0.23 |

We estimate that, net of home internet, our shelter term adds 0.27–4.33 points in
every tenure and year, and it supplies most of the owners' excess. Imputed
benefits lower owners' gaps in every year, because our school lunch trails BLS's,
and add 0.11–1.36 points to the renter gap, because our rental assistance per renter exceeds
BLS's. From 2019 to 2023, that renter term exceeds renters' shelter net of home
internet. Our clothing term trails BLS's by 0.24–0.96 points, and food, telephone
and utilities stay within 0.81 points. For BLS's home internet, we use the
workbook's internet row with equal dollars across tenures, since that row
balances the second identity, and subtract the band's mean broadband subsidy.
That home internet term supplies 1.85–2.55% of BLS's thresholds with Other
spread and 1.54–2.12% with Other separate.

With Other separate, the food, clothing, telephone, school lunch and WIC
terms, and home internet together with broadband, fall by a sixth. The
shelter, utilities, rental assistance and LIHEAP terms lose their parts of
`0.2 × F`, and the other term gathers all those parts, adding 0.19–0.36
points to the gap:

| Term | Renter | Owner with mortgage | Owner without mortgage |
|---|---:|---:|---:|
| Imputed benefits | +0.13 to +1.26 | −0.33 to −0.13 | −0.52 to −0.16 |
| Shelter | +1.83 to +3.31 | +2.30 to +3.02 | +4.34 to +6.07 |
| Home internet | −1.78 to −1.55 | −1.78 to −1.54 | −2.12 to −1.83 |
| Utilities | −0.29 to +0.26 | +0.04 to +0.36 | −0.80 to +0.70 |
| Food | −0.04 to +0.38 | −0.04 to +0.39 | −0.05 to +0.46 |
| Clothing | −0.68 to −0.20 | −0.67 to −0.20 | −0.80 to −0.24 |
| Telephone | −0.07 to +0.16 | −0.08 to +0.16 | −0.09 to +0.19 |
| Other (0.2 × FCSUti) | +0.19 to +0.30 | +0.20 to +0.30 | +0.24 to +0.36 |

Net of home internet, we estimate that our shelter term then adds 0.09–3.97
points, and imputed benefits add 0.13–1.26 points to the renter gap.

### BLS's written shelter, utilities and food definitions

BLS's papers define shelter, utilities and food more narrowly than the CE
summaries the replication reads. [Garner and Munoz (2021)](https://www.bls.gov/pir/spm/garner_spm_choices_03_15_21.pdf)
restrict shelter to the primary residence, and leave rent as pay out of
renters' shelter and meals as pay out of food. They count owners' utilities for
the primary residence only and renters' utilities for every property except
rented vacation homes. The CE's `SHELT` also holds other lodging (vacation
homes, housing while attending school and lodging on out-of-town trips) and
rent as pay. Its `UTIL` also holds utilities for owned and rented vacation
homes, and
its `FOOD` holds meals as pay
([CE glossary](https://www.bls.gov/cex/csxgloss.htm),
[PUMD dictionary](https://www.bls.gov/cex/pumd/ce-pumd-interview-diary-dictionary.xlsx)).
The replication adds vacation-home mortgage principal to shelter as well. BLS
has not published the code behind its current thresholds, so its practice may
differ from these papers.

In-band shelter per unit of each tenure, ours less BLS's, with the amounts BLS's
papers leave out in parentheses, beside BLS's in-band home internet:

| Target | Renter | Owner with mortgage | Owner without mortgage | BLS home internet |
|---|---:|---:|---:|---:|
| 2019 | \$695 (\$392) | \$851 (\$312) | \$1,299 (\$1,143) | \$547 |
| 2020 | \$765 (\$451) | \$1,054 (\$332) | \$1,634 (\$1,350) | \$598 |
| 2021 | \$878 (\$471) | \$955 (\$324) | \$1,763 (\$1,104) | \$656 |
| 2022 | \$855 (\$421) | \$989 (\$403) | \$1,511 (\$923) | \$718 |
| 2023 | \$829 (\$399) | \$1,036 (\$498) | \$1,732 (\$865) | \$787 |
| 2024 | \$1,581 (\$370) | \$1,291 (\$502) | \$2,011 (\$1,305) | \$852 |
| 2025 | \$992 (\$388) | \$1,523 (\$519) | \$2,541 (\$1,379) | \$878 |

Other lodging, vacation-home principal and rent as pay make up 23–88% of the
shelter excess, and other lodging alone 15–86%. Meals as pay add \$17–\$31 to
in-band food.

`apply_bls_paper_definition` removes those four amounts and vacation-home
utilities from the raw FMLI columns before the replication builds its CPI
weights, price factors and bands. FMLI summarizes utilities for owned vacation
homes in `UTILOWN` and for rented ones in `UTILRNT`, so the function removes
both from owners' utilities and only `UTILRNT` from renters'. Those summaries
leave out coal, wood and other fuels for vacation homes (UCCs 250913 and
250914), so those fuels stay in `UTIL`. In our band, we estimate that the
removed vacation-home utilities average \$15–\$52 per owner without a mortgage,
\$5–\$19 per owner with one and \$0–\$3 per renter.

Signed gap from BLS's corrected thresholds in percent under these definitions,
without → with the stage:

| Target | Renter | Owner with mortgage | Owner without mortgage |
|---|---:|---:|---:|
| 2019 | −2.91 → −0.18 | −3.53 → −0.88 | −3.90 → +0.29 |
| 2020 | −3.28 → −0.44 | −3.53 → −1.13 | −3.35 → +1.47 |
| 2021 | −2.74 → −0.31 | −3.26 → −0.83 | −2.35 → +0.33 |
| 2022 | −2.59 → +0.61 | −3.07 → −0.30 | −2.22 → −0.31 |
| 2023 | −3.13 → −0.10 | −3.56 → −0.85 | −2.02 → +0.53 |
| 2024 | −2.46 → +0.20 | −4.20 → −1.17 | −3.59 → −1.73 |
| 2025 | −4.15 → −1.04 | −4.09 → −1.28 | −1.98 → −1.32 |

With BLS's FCSUti index as the deflator:

| Target | Renter | Owner with mortgage | Owner without mortgage |
|---|---:|---:|---:|
| 2019 | −2.37 → +0.27 | −3.17 → −0.48 | −3.38 → +0.74 |
| 2020 | −2.65 → −0.09 | −3.26 → −0.70 | −2.94 → +1.97 |
| 2021 | −2.85 → −0.29 | −3.13 → −0.89 | −2.53 → +0.63 |
| 2022 | −3.00 → +0.26 | −3.36 → −0.68 | −2.53 → −0.78 |
| 2023 | −3.09 → −0.06 | −3.63 → −0.81 | −1.83 → +0.39 |
| 2024 | −2.14 → +0.54 | −3.75 → −0.72 | −3.15 → −1.75 |
| 2025 | −3.55 → −0.33 | −3.49 → −0.73 | −2.28 → −0.34 |

Under these definitions, the out-of-pocket replication trails BLS in every
tenure and year, by 1.98–4.20% with the package CPI. The stage cuts the mean
absolute gap from 3.14% to 0.73%, and 6 of the 21 cells land above BLS. Under
the replication's own definitions, the stage raises the mean absolute gap from
1.36% to 1.76%, and all 21 land above BLS. With BLS's index and these
definitions, the stage cuts it from 2.96% to 0.64%.

Each term's part of the gap under these definitions, in percentage points of
BLS's threshold, with Other spread:

| Term | Renter | Owner with mortgage | Owner without mortgage |
|---|---:|---:|---:|
| Imputed benefits | −0.08 to +1.41 | −0.40 to −0.01 | −0.59 to −0.01 |
| Shelter | +1.01 to +2.26 | +1.35 to +1.97 | +2.02 to +4.63 |
| Home internet | −2.14 to −1.86 | −2.14 to −1.85 | −2.55 to −2.20 |
| Utilities | −0.35 to +0.18 | −0.04 to +0.27 | −1.08 to +0.59 |
| Food | −0.29 to +0.54 | −0.29 to +0.54 | −0.34 to +0.65 |
| Clothing | −0.93 to −0.18 | −0.92 to −0.18 | −1.09 to −0.21 |
| Telephone | −0.14 to +0.29 | −0.14 to +0.30 | −0.17 to +0.35 |

When we adopt these definitions, we estimate 17–62% less in the shelter term,
45% less on average, and what remains roughly offsets the omitted home internet
term. Net of home internet, we estimate gaps of −1.06 to +0.13 points for
renters, −0.75 to −0.05 for owners with mortgages and −0.47 to +2.30 for owners
without mortgages. We have not traced the remaining shelter excess.

The same terms with Other separate:

| Term | Renter | Owner with mortgage | Owner without mortgage |
|---|---:|---:|---:|
| Imputed benefits | −0.04 to +1.30 | −0.35 to −0.11 | −0.53 to −0.14 |
| Shelter | +0.78 to +1.90 | +1.04 to +1.61 | +1.75 to +4.19 |
| Home internet | −1.78 to −1.55 | −1.78 to −1.54 | −2.13 to −1.83 |
| Utilities | −0.30 to +0.16 | −0.01 to +0.25 | −1.06 to +0.56 |
| Food | −0.24 to +0.45 | −0.24 to +0.45 | −0.28 to +0.54 |
| Clothing | −0.77 to −0.15 | −0.77 to −0.15 | −0.91 to −0.17 |
| Telephone | −0.12 to +0.25 | −0.12 to +0.25 | −0.14 to +0.29 |
| Other (0.2 × FCSUti) | −0.12 to +0.02 | −0.12 to +0.02 | −0.14 to +0.03 |

### Imputed amounts and threshold growth

In-band amounts, 2022 to 2025:

| Series | All imputed benefits | Rental assistance per renter | School lunch |
|---|---:|---:|---:|
| BLS | \$855 → \$1,257 (+\$401) | \$738 → \$1,243 (+\$505) | \$500 → \$742 (+\$242) |
| Ours, package CPI | \$1,024 → \$1,175 (+\$151) | \$1,335 → \$1,464 (+\$129) | \$425 → \$571 (+\$146) |
| Ours, FCSUti index | \$1,020 → \$1,214 (+\$194) | \$1,328 → \$1,522 (+\$195) | \$422 → \$579 (+\$157) |

BLS's imputed benefits rise \$401 and ours \$151 with the package CPI, and
BLS's rise exceeds all five of our implicates' with either deflator
(\$34–\$303). Across all units in the band, rental assistance supplies \$162 of
that difference and school lunch \$97. From the 2019 to the 2022 thresholds,
BLS's rental assistance per renter rose 17%, and we estimate that ours rose 20%.
For the 2019–2023 thresholds, we estimate rental
assistance per renter 70 to 81% above BLS's, \$1,335 against \$738 in 2022.
From 2022 to 2025, BLS's amount rose by \$505, and we estimate that ours rose by
\$129, with a standard error of \$438 ([Rises in imputed
amounts](#rises-in-imputed-amounts)). BLS draws on many of the same CE
interviews, so that standard error does not measure the sampling error in the
gap between the two rises. We have not established what produces the level gap
or what raised BLS's amount in 2024 and 2025.

The imputed terms in each threshold, 2022 to 2025. Each cell lists renters /
owners with mortgages / owners without mortgages. The share of growth beyond
CPI-U equals `(I_2025 − π × I_2022) / (T_2025 − π × T_2022)`, where `I` sums the
imputed terms in threshold `T` under each accounting and `π` = 1.1001, CPI-U's
ratio. In the last two columns, we hold each band fixed and compare threshold
growth with and without those terms.

| Series | Share of growth beyond CPI-U, Other spread, % | Share of growth beyond CPI-U, Other separate, % | Points of growth, Other spread | Growth without imputed terms, Other spread, % |
|---|---:|---:|---:|---:|
| BLS | 12.9 / 4.9 / 7.6 | 11.8 / 3.5 / 5.8 | +1.18 / +0.38 / +0.60 | 20.97 / 21.23 / 20.03 |
| Ours, package CPI | 2.3 / 2.2 / 2.8 | 2.2 / 1.9 / 2.5 | −0.26 / +0.07 / +0.10 | 20.00 / 21.13 / 19.72 |
| Ours, FCSUti index | 3.9 / 2.5 / 2.8 | 3.6 / 2.0 / 2.4 | −0.10 / +0.11 / +0.12 | 20.98 / 21.99 / 21.64 |

Threshold growth with the stage less BLS's, in percentage points, with imputed
terms kept → removed from both series:

| Tenure | Replication's definitions, package CPI | Replication's definitions, FCSUti index | BLS's written definitions, package CPI | BLS's written definitions, FCSUti index |
|---|---:|---:|---:|---:|
| Renter | −2.41 → −0.97 | −1.26 → +0.02 | −2.00 → −0.44 | −0.71 → +1.00 |
| Owner with mortgage | −0.41 → −0.10 | +0.48 → +0.75 | −1.20 → −0.88 | −0.06 → +0.28 |
| Owner without mortgage | −0.81 → −0.31 | +1.13 → +1.61 | −1.22 → −0.72 | +0.53 → +1.07 |

Removing imputed terms from both series narrows the renter shortfall from −2.41
to −0.97 points with the package CPI and closes it with BLS's index (−1.26 to
+0.02). Owners' figures move by 0.27–0.54 points. Those renter figures with
imputed terms removed carry between-implicate standard deviations of 0.40–0.63
points. BLS's thresholds draw on the same CE interviews as ours, so the
[standard errors of growth](#growth-from-2022-to-2025) do not measure how much
of these gaps sampling could explain.

Holding each band fixed leaves out rank shifts. The stage also reorders
units, which moves the replication's 2022–2025 growth by a further −0.37 points
for renters, −0.01 for owners with mortgages and +0.94 for owners without
mortgages. BLS publishes no unit-level values, so we can't measure its rank
shifts.

2022–2025 growth with the stage, under each definition and deflator:

| Tenure | BLS corrected | Replication's definitions, package CPI | Replication's definitions, FCSUti index | BLS's written definitions, package CPI | BLS's written definitions, FCSUti index |
|---|---:|---:|---:|---:|---:|
| Renter | +22.15% | +19.74% | +20.88% | +20.14% | +21.43% |
| Owner with mortgage | +21.61% | +21.21% | +22.10% | +20.42% | +21.55% |
| Owner without mortgage | +20.63% | +19.82% | +21.76% | +19.41% | +21.16% |

Using BLS's written definitions and BLS's index, we estimate 2022–2025 growth
with the stage within 0.8 points of BLS's for every tenure.

## Sampling uncertainty

The CE Interview Survey's public-use files carry 44 replicate weights,
`WTREP01`–`WTREP44`, beside the full-sample weight `FINLWT21`. BLS builds them
by balanced repeated replication: it divides the sampled primary sampling units
into 43 strata and splits each stratum's consumer units at random into two half
samples. Each replicate keeps one half sample per stratum, and BLS picks the
44 combinations with a 44 × 44 Hadamard matrix
([Handbook of Methods](https://www.bls.gov/opub/hom/cex/calculation.htm)). We
rerun each estimate `θ` under each replicate weight `r` and estimate its
variance as

```text
V = Σ_r (θ_r − θ)² / (44 × (1 − k)²)
```

BLS used the standard form, `k = 0`, through 2024 CE data and switched to
Fay's method, `k = 0.5`, with 2025 data
([CE standard errors](https://www.bls.gov/cex/ce-standarderrors.htm)). Our
windows draw on the 2014–2024 releases, whose interviews run from 2014Q2
through 2025Q1, so we set `k = 0`. In each of those quarters, every record
carries 22 positive and 22 blank replicate weights, and
`scripts/estimate_ce_replicate_uncertainty.py` stops on any other pattern.

We rerun the whole replication under each replicate's weights. Consumer units
with a zero weight drop out, and the package deflator's CPI component weights,
the 47th–53rd percentile band and the band means all follow the replicate's
weights. With the stage, we add each implicate's imputed amounts to the same
units before we select the band. Each record keeps its replicate weights in
every window that holds it, so the standard errors of growth account for the
quarters two windows share, eight between the 2022 and 2025 windows.

We keep each implicate's imputed amounts from the full-sample run in every
replicate. We fit the CPS ASEC participation and amount models and the CE rent
model once, with full-sample weights. For each implicate, we draw the models'
parameters from their estimated sampling distributions, so the spread across
implicates carries part of the models' estimation uncertainty. Those distributions treat units as
independent and leave out the CPS ASEC's and the CE's strata and clusters, and
the replicates never refit the models. The CE income behind each unit's
poverty ratio, `FINCBTXM`, averages BLS's five income imputations, so their
spread stays out as well. In the FCSUti run, we take every price factor from
BLS's published index, so the factors stay the same in every replicate.

From one quarter to the next, every consumer unit interviewed in both keeps its
pattern of positive and blank replicate weights, except across two pairs of
quarters. Of the units interviewed in both 2015Q1 and 2015Q2, 1.9% of 2,644 keep
it, and of those interviewed in both 2016Q4 and 2017Q1, 3.4% of 3,979 do. A
changed unit's interviews before and after can then fall in different half
samples under one replicate number, so the replicates can miss part of the
correlation between those interviews. The 2019 window spans both changes, the
2020 and 2021 windows span 2017Q1, and the 2022–2025 windows span neither.

With the stage, we combine the five implicates by Rubin's rules (Rubin 1987):
the total variance adds the implicates' mean replicate variance to 1.2 times the
variance of their full-sample estimates. Degrees of freedom follow
Barnard and Rubin (1999), with the 43 strata as complete-data degrees of
freedom, and figures without the stage keep 43. Each estimate below comes from
the mean threshold across implicates, and each growth figure differs from
Rubin's mean of the implicates' growth by at most 0.01 points.

`scripts/estimate_ce_replicate_uncertainty.py` reruns all 44 replicates for
2019–2025 under both deflators and writes
`spm_calculator/data/current/ce_replicate_uncertainty_2019_2025.json`, which
stores every replicate's estimate. The script stops unless the full-sample run
reproduces the thresholds and band amounts above.

### Levels

Standard errors of each threshold in dollars with the package CPI, without the
stage / with the stage / BLS's published standard error:

| Year | Renter | Owner with mortgage | Owner without mortgage |
|---|---:|---:|---:|
| 2019 | 208 / 239 / 204 | 198 / 222 / 201 | 347 / 406 / 328 |
| 2020 | 205 / 260 / 257 | 215 / 249 / 224 | 440 / 380 / 334 |
| 2021 | 185 / 243 / 242 | 243 / 291 / 286 | 505 / 465 / 259 |
| 2022 | 291 / 239 / 308 | 322 / 324 / 319 | 542 / 612 / 439 |
| 2023 | 235 / 238 / 345 | 293 / 326 / 330 | 697 / 670 / 517 |
| 2024 | 215 / 235 / 325 | 410 / 361 / 303 | 690 / 828 / 682 |
| 2025 | 327 / 373 / 393 | 400 / 382 / 327 | 569 / 822 / 560 |

With the stage, our standard errors run 0.69–1.17 times BLS's published ones
for renters, 0.99–1.19 times for owners with mortgages and 1.14–1.79 times for
owners without mortgages. BLS's index shifts each end of
those ranges by 0.06 or less. Our standard errors equal 0.59–0.94% of the
threshold for renters and owners with mortgages and 1.45–2.47% for owners
without mortgages, who make up fewer than one in ten units in the band. Sampling supplies at least 78% of each level's variance, and
the degrees of freedom range from 23 to 41. BLS publishes a standard error for
each threshold in its workbooks. Garner (2010) computed the standard errors
of BLS's 2006–2008 experimental thresholds by balanced repeated replication
with the CE's 44 replicate weights
([BLS Working Paper 436](https://www.bls.gov/osmr/research-papers/2010/pdf/ec100040.pdf)),
as we do, and Garner and Gudrais (2018) base theirs on the same 44
replicates. BLS's methods page and workbooks do not say how its current
replicates treat the percentile band or the imputed benefits. Its
thresholds draw on the same CE interviews as ours, so these standard errors do not measure how much of any gap
to BLS sampling could explain.

### Growth from 2022 to 2025

2022–2025 growth, with standard errors in parentheses. The degrees of freedom
belong to the stage's change, and the last column removes the imputed terms from
both thresholds, as in the
[comparison with BLS components](#imputed-amounts-and-threshold-growth):

| Tenure | Without the stage | With the stage | Stage's change, points | Degrees of freedom | Imputed terms removed |
|---|---:|---:|---:|---:|---:|
| Package composite CPI |  |  |  |  |  |
| Renter | +20.37% (0.99) | +19.74% (1.18) | −0.63 (0.99) | 11 | +20.00% (1.51) |
| Owner with mortgage | +21.15% (1.09) | +21.21% (1.05) | +0.06 (0.75) | 17 | +21.13% (1.08) |
| Owner without mortgage | +18.79% (2.63) | +19.82% (2.92) | +1.04 (2.57) | 24 | +19.72% (3.00) |
| BLS's FCSUti index |  |  |  |  |  |
| Renter | +21.48% (1.00) | +20.88% (1.11) | −0.60 (0.89) | 14 | +20.98% (1.44) |
| Owner with mortgage | +22.08% (1.10) | +22.10% (1.10) | +0.01 (0.77) | 11 | +21.99% (1.14) |
| Owner without mortgage | +20.81% (2.61) | +21.76% (3.03) | +0.95 (2.62) | 27 | +21.64% (3.12) |

The stage's change in 2022–2025 growth lies within one standard error of zero in
every tenure with either deflator, and the largest, renters' −0.60 points with
BLS's index, reaches 0.67 standard errors. With the package CPI, 95% intervals
for the change run from −2.81 to +1.55 points for renters, −1.52 to +1.64 for
owners with mortgages and −4.28 to +6.35 for owners without. The
implicates' spread supplies 17–44% of each change's variance, and the degrees of
freedom fall to 11–27. Growth with and without the stage carries standard errors
of 0.99–1.18 points for renters and owners with mortgages and 2.61–3.03 for
owners without mortgages.

### Yearly growth

The stage's change in each year's growth with the package CPI, in percentage
points, with standard errors:

| Years | Renter | Owner with mortgage | Owner without mortgage |
|---|---:|---:|---:|
| 2019–2020 | −0.11 (0.38) | +0.13 (0.27) | −0.01 (1.59) |
| 2020–2021 | +0.42 (0.39) | −0.32 (0.35) | −1.59 (1.77) |
| 2021–2022 | +0.49 (0.66) | +0.24 (0.48) | −0.79 (2.30) |
| 2022–2023 | −1.11 (0.77) | +0.49 (0.51) | +0.71 (2.55) |
| 2023–2024 | +0.57 (0.67) | −0.14 (0.51) | −1.28 (2.84) |
| 2024–2025 | −0.05 (0.51) | −0.29 (0.49) | +1.45 (2.18) |

No yearly change reaches two standard errors with either deflator: the largest,
renters' change from 2022 to 2023, reaches 1.45 with the package CPI and 1.50
with BLS's index. With the package CPI, each year's growth carries standard
errors of 0.36–0.63 points for renters and owners with mortgages and 1.21–2.55
for owners without mortgages. For example, renter growth from 2024 to 2025 runs
4.80% with the stage and 4.85% without it, with standard errors of 0.63 and 0.59
points.

### Rises in imputed amounts

The 2022–2025 rise in mean in-band amounts, BLS's beside ours with standard
errors:

| Amount | BLS | Package composite CPI | BLS's FCSUti index |
|---|---:|---:|---:|
| All imputed benefits | +\$401 | +\$151 (196) | +\$194 (182) |
| Rental assistance per renter | +\$505 | +\$129 (438) | +\$195 (402) |
| School lunch | +\$242 | +\$146 (50) | +\$157 (51) |

With the package CPI, our in-band amounts carry standard errors of \$103–\$127 a
year for all imputed benefits, \$210–\$303 for rental assistance per renter and
\$15–\$35 for school lunch. The two windows' band amounts barely move together:
within each implicate and under either deflator, their replicate deviations
correlate at −0.26 to +0.22, so each rise's standard error exceeds both years'.
With either deflator, the implicates' spread supplies 30–47% of each rise's
variance.

## Limitations

- BLS has not published its imputation code. The models here follow its
  methods page, and their covariates differ from the set Garner and Gudrais
  (2018) list for BLS's earlier models.
- The rental model is a log-normal Tobit on CE unit characteristics and
  takes reported rents as exact. It fits each reference year separately and
  draws each market rent, where Garner and Gudrais (2018) pool the window's
  years and assign each assisted unit its predicted rent. The public files
  do not identify rent-controlled units, and the market-rent fit keeps
  renters who receive reduced rent as pay.
- School lunch donor values for reference years 2014–2017 come from the
  USDA formula; later years use Census `SPM_SCHLUNCH` values.
- BLS says it assigns school lunch by the traditional method before and
  after the COVID-19 period. The stage uses Census's `SPM_SCHLUNCH` values
  for every reference year from 2018, and from reference year 2023 Census
  estimates those values with its fall 2022 method (Census SPM technical
  documentation).
- The imputation assigns school lunch only to households it imputes as
  receiving free, reduced-price or universal-free lunch. Census also
  values paid lunches and, in some years, P-EBT or Summer EBT for
  households without free or reduced-price lunch.
- Census accounts for P-EBT in its school lunch values for reference years
  2020 and 2021, and states paid P-EBT on EBT cards. BLS says it follows
  Census's COVID-era methods, so the stage does too, but by BLS's reasoning
  for leaving out SNAP, reported food spending may already include those
  benefits.
- WIC uses USDA's national fiscal-year average food cost; Census has used
  state averages since its revised 2019 estimates.
- All participation models share one covariate set across programs and
  years, and the CE and CPS income concepts differ.
- The replication still omits home internet spending.
- From reference year 2020, we add no WIC in any state, though FNS dates six
  states and DC after the statutory deadline. With each state's own date, we
  estimate that the 2021–2025 thresholds move by −\$20 to +\$40.
- BLS's written shelter, utilities and food definitions come from Garner and
  Munoz (2021). BLS's thresholds also carry later refinements and corrections,
  so its current practice may differ. FMLI's vacation-home utility summaries
  leave out coal, wood and other fuels for vacation homes, so the definition
  runs keep those fuels.
- We hold each band fixed when we compare growth with BLS, and BLS publishes
  no unit-level values that would show its rank shifts.
- We hold each implicate's imputed amounts fixed across the CE replicates and
  never refit the imputation models, whose parameter draws come from
  covariances that treat units as independent. The CE income behind each
  unit's poverty ratio averages BLS's five income imputations, so the standard
  errors leave out their spread.
- Most consumer units interviewed across 2015Q1 and 2015Q2, or across 2016Q4
  and 2017Q1, changed replicate patterns, so the replicates for the 2019–2021
  windows can miss part of the correlation between a unit's interviews.

## Run it

The imputation runs as an optional stage. It composes the public functions
of `spm_calculator.ce_threshold` and leaves the default replication
unchanged.

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

## Forecast windows: a proposed design

The stage covers observed windows only. The
[rolling forecasts](rolling-forecasts.md) project a future window by
copying same-season donor quarters, keeping each donor's `NEWID`, and
scaling monetary columns, then anchor national levels as
`published_2025 × replication_T / replication_2025`. A follow-up could
carry the stage into those windows:

1. Impute the window's observed quarters with the latest CPS ASEC donors
   and give each projected copy its donor's amounts. Projected copies keep
   their donor's `NEWID`, and the stage requires each `NEWID` to appear
   once.
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
- `spm_calculator/ce_bls_shares.py`: in-band components for BLS and the
  replication, and BLS's written shelter, utilities and food definitions.
- `spm_calculator/data/current/bls_spm_shares.xlsx`: BLS's threshold shares
  ([source](https://www.bls.gov/pir/spm/spm_shares.xlsx)).
- `scripts/compare_ce_inkind_bls_shares.py` and
  `spm_calculator/data/current/ce_inkind_bls_components_2019_2025.json`:
  the comparison and its receipt. `scripts/render_ce_inkind_bls_tables.py`
  prints this page's comparison tables from the receipt.
- `spm_calculator/ce_replicates.py`: replicate weights, replicate variances,
  Rubin's rules and the replicate runs.
- `scripts/estimate_ce_replicate_uncertainty.py` and
  `spm_calculator/data/current/ce_replicate_uncertainty_2019_2025.json`: the
  replicate runs and their receipt, which stores every replicate's estimate.
  `scripts/render_ce_replicate_tables.py` prints this page's standard error
  tables from the receipt.
