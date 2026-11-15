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
benefits and home internet spending by default. We add home internet from
the CE's detailed expenditure file and rerun the 2019–2025 thresholds three
ways: without home internet or benefits, with home internet, and with home
internet and benefits. Each step's effect then reads off directly, for the
replication's gap to BLS's corrected thresholds and for threshold growth.

- We estimate that home internet raises the replication's thresholds by
  1.5–2.4% for renters, 1.7–2.1% for owners with mortgages and 0.3–4.0% for
  owners without mortgages. With home internet and without benefits, our
  in-band home internet comes within 4.1% of BLS's in every year, renters and
  owners with mortgages land within about 1% of BLS's corrected levels, and
  owners without mortgages 2.0–4.5% above.
- Imputed benefits then raise thresholds by 0.5–3.5% and carry them 2.2–7.1%
  above BLS's for every tenure in every year. When we give each component its
  part of BLS's 1.2 multiplier, we estimate that our shelter term supplies at
  least 60% of each gap, and our rental assistance adds to the renter gap.
  BLS's papers define shelter, utilities and food more narrowly than the
  replication does, and under those definitions the replication with home
  internet and benefits lands 0.8–3.6% above BLS.
- We estimate that home internet changes 2022–2025 threshold growth by
  −0.54 points for renters, +0.01 for owners with mortgages and +4.33 for
  owners without mortgages. Owners without mortgages hold less than a tenth
  of the band by weight, so units entering and leaving it move their mean.
  We estimate that imputed benefits then change growth by −0.27, −0.17 and
  −1.63 points, each within one standard error of zero.
- Without home internet, deflating with BLS's FCSUti index instead of the
  package's composite CPI brings the replication within 0.7 points of BLS's
  2022–2025 growth for every tenure. With home internet and BLS's index,
  renters' growth trails BLS's by 1.0 points and owners' runs 0.5 and 2.4
  points ahead.
- We compute BLS's in-band dollars from its published shares. Our imputed
  total exceeds BLS's through 2024 and trails it in 2025. From 2022 to 2025,
  BLS's imputed benefits rise \$401 and ours \$143, and removing imputed terms
  from both narrows the renter growth shortfall from −2.59 to −1.10 points.

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
middle of the unit's reference period. Where the CE withholds the state, we
count the unit's state as finished with probability equal to the weighted
share of known-state units in its region and collection quarter whose state
had finished. From reference year 2020, the year of the statutory deadline,
we add no WIC in any state, even where the middle of a unit's reference
period falls before the deadline. Six states finished during 2020 before
October 1, from Hawaii in June to Illinois in September. FNS dates six other
states and DC after the deadline, from Utah in November 2020 to Georgia in
October 2022. In both groups, we would add WIC to some units if we applied
BLS's rule strictly, state by state.
With each state's own date in every year, we estimate that mean WIC per
unit rises by \$1.94–\$3.20 for the 2021–2025 targets. Those thresholds move
by −\$5 to +\$18 (−0.01% to +0.05%) as the added WIC reorders units in the
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

### Home internet

BLS's FCSUti also counts "home internet service expenditures" ([SPM
thresholds methods](https://www.bls.gov/pir/spmhome.htm)). The FMLI file has
no internet summary, so the package's replication omits them. We take each
unit's three-month cost for UCC 690114, "Computer information services",
from the MTBI expenditure file in the same CE bundle and quarter, multiply it
by four and add it to FCSUti but not SU. BLS's CE-to-CPI concordance
([CPI Handbook of Methods, Appendix
5](https://www.bls.gov/cpi/additional-resources/ce-cpi-concordance.htm))
maps that UCC to ELI EE031, "Internet access and other information
services". It maps UCC 690116, internet services away from home, to the same
ELI. We leave 690116 out because BLS counts home internet. Among units with
children, 690116 would add 0.4–1.2% to 690114 spending in each target year's
window, and 690114 alone comes within 1% of BLS's in-band home internet for
the 2019 thresholds. BLS has not published the UCCs behind its home internet
term.

We count home internet as out-of-pocket spending in its own component, and
none of our imputed totals, imputed shares or imputed contributions includes
it. We price it with CPI-U series CUUR0000SEEE03, "Internet
services and electronic information providers", which
`scripts/fetch_internet_cpi.py` pins with BLS's API responses in
`spm_calculator/data/bls/cpi_internet_receipt.json`. The series joins the
package's FCSUti composite at internet's spending share among units with
children, the rule the composite already applies to its other components,
and the other weights scale down in proportion. We recompute each unit's
price factor from that composite and reprice its unchanged SU spending at
the same factor.

Two CE changes reach UCC 690114. BLS's thresholds draw on the same Interview
quarters, so if its home internet term draws on this UCC, as the close match
in every year suggests, its series carries both. In 2017Q2 the share of units
reporting the UCC drops for one quarter and recovers in 2017Q3, while the
mean among reporters steps up and stays higher; the share reporting cable
and satellite TV falls in the same quarter. BLS's list of CE [improvements
and protocol changes](https://www.bls.gov/cex/ce-improvements.htm) shows no
2017 change to the Interview's telephone, internet and cable or satellite TV
questions. But BLS's [2017 data quality
profile](https://www.bls.gov/cex/dqreport2017.pdf) (p. 12) reports a change
in processing. Beginning in 2017, BLS allocates combined bills for these
services across them by proportions from a pool of donors, where it
previously imputed them. The CE's cost flags ([PUMD Getting Started
Guide](https://www.bls.gov/cex/pumd-getting-started-guide.htm), Table 2)
date the change to 2017Q2: among UCC 690114 records, the share flagged as
imputed or otherwise adjusted falls from 44% in 2017Q1 to none, and the
share flagged as allocated rises from 25% to 65%. That change likely causes
the break, though we have not confirmed it. The 2019–2021 thresholds, whose
windows run from 2014Q2–2019Q1 to 2016Q2–2021Q1, span the break, and the 2022
thresholds' window, 2017Q2–2022Q1, starts at it. In 2024 BLS revised the
Interview questions on cable, internet, residential and cellular phone
service and dropped the follow-up questions on bundled amounts ([improvements
list](https://www.bls.gov/cex/ce-improvements.htm)); the share reporting
690114 changes little across the revision.

### Where the amounts enter

Every component enters FCSUti. LIHEAP and rental assistance pay for
utilities and shelter, so they also enter SU, which sets the
tenure-specific part of each threshold,
`0.82 × (1.2 × FCSUti_E − SU_E + SU_Eh)`. The stage carries reference-year
amounts to the threshold year with the price factor the replication
applies to the same unit's out-of-pocket spending, and keeps the CPI
component weights of out-of-pocket spending, home internet included.

The stage never lowers any unit's FCSUti or SU, yet a single component
can still lower a tenure's threshold: added benefits reorder units and
change which of them land in the 47th–53rd percentile band. In 2025, we
estimate that rental assistance alone lowers the threshold for owners
without mortgages by 1.25%.

## Invariants

1. Imputed amounts are finite and nonnegative for every unit and
   component.
2. The stage never lowers any unit's FCSUti or SU.
3. An all-zero in-kind table reproduces the out-of-pocket thresholds,
   estimation diagnostics and normalized expenditures exactly, with home
   internet included. The default replication runs no in-kind or home
   internet code.
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
17. Zero home internet spending reproduces the package's out-of-pocket run
    exactly, and with no internet weight the composite price factor equals
    the package's. With every other series flat, the factor equals
    1 − w + w × r, where w is internet's CPI weight and r the ratio of
    CPI-U series CUUR0000SEEE03 between the two years.
18. Each unit's home internet cost equals the sum of its MTBI records for
    UCC 690114, and internet's CPI weight equals its spending share among
    units with children.

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

`tests/test_ce_internet.py` checks invariants 17 and 18 with Hypothesis
property tests and fixtures on synthetic data, and checks invariant 3 with
home internet included in a Hypothesis property test. It ties unit costs to the
MTBI records in 2017Q2, 2019Q1 and 2024Q3 when those CE bundles are cached,
and checks that replicates add home internet as the full-sample run does.

`tests/test_ce_replicates.py` checks invariants 12–15 with Hypothesis
property tests on synthetic data and invariant 16 on a fixture. It holds each
replicate to the stage's public functions run on the reweighted sample and
Rubin's rules to a separate implementation. It recomputes every standard error
in the [sampling uncertainty](#sampling-uncertainty) receipt from the
replicates the receipt stores, and it fails when the receipt no longer matches
its code or the page's tables no longer match the receipt.

## Results

All figures come from the committed receipt, five implicates, with CPI
pinned to the package's `cpi_annual.json`, plus the home internet series in
`cpi_internet_receipt.json`, unless a section says otherwise. We estimate
thresholds on consumer units with children.

### Imputed amounts

Mean amount per consumer unit in the estimation sample, in threshold-year
dollars:

| Target | School lunch | WIC | LIHEAP | Broadband | Rental assistance | Total | Share with any |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2019 | 321 | 52 | 18 | 0 | 446 | 837 | 34.0% |
| 2020 | 344 | 44 | 18 | 0 | 443 | 849 | 34.7% |
| 2021 | 335 | 32 | 18 | 0 | 454 | 838 | 33.1% |
| 2022 | 424 | 23 | 22 | 0 | 485 | 954 | 36.3% |
| 2023 | 507 | 13 | 26 | 3 | 479 | 1,028 | 38.5% |
| 2024 | 550 | 6 | 26 | 7 | 504 | 1,093 | 39.8% |
| 2025 | 585 | 0 | 26 | 8 | 528 | 1,148 | 41.0% |

School lunch and rental assistance supply over 90% of the total in every
year. School lunch grows the most, from \$321 to \$585 a unit. Among CPS
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

Signed gap from BLS's corrected thresholds in percent, without home internet
or benefits → with home internet → with home internet and benefits:

| Target | Renter | Owner with mortgage | Owner without mortgage |
|---|---:|---:|---:|
| 2019 | −1.12 → +0.39 → +3.64 | −1.67 → −0.03 → +2.51 | −1.00 → +2.48 → +4.94 |
| 2020 | −1.45 → +0.08 → +3.43 | −1.69 → +0.13 → +2.87 | −0.24 → +3.28 → +4.99 |
| 2021 | −1.36 → +0.63 → +3.76 | −1.55 → +0.32 → +2.79 | +0.78 → +2.59 → +5.68 |
| 2022 | −1.33 → +1.02 → +4.40 | −1.41 → +0.52 → +3.10 | +1.67 → +2.01 → +5.63 |
| 2023 | −1.07 → +0.74 → +3.70 | −2.05 → +0.05 → +2.77 | +0.72 → +3.41 → +7.06 |
| 2024 | −1.40 → +0.75 → +3.64 | −2.25 → −0.19 → +2.77 | +1.14 → +4.50 → +5.05 |
| 2025 | −2.77 → −0.90 → +2.18 | −1.79 → +0.14 → +2.56 | +0.11 → +4.12 → +6.38 |

The first figure in each cell comes from the [September 8
replication](current-ce-replication.md)'s thresholds, which our run without
home internet or benefits reproduces exactly. Each step's effect in percent of
the threshold before it (home internet / benefits), with the between-implicate
standard deviation of the threshold with home internet and benefits in
parentheses, in percent of that threshold:

| Target | Renter | Owner with mortgage | Owner without mortgage |
|---|---:|---:|---:|
| 2019 | +1.53 / +3.24 (0.13) | +1.66 / +2.54 (0.07) | +3.51 / +2.41 (0.29) |
| 2020 | +1.55 / +3.36 (0.18) | +1.86 / +2.73 (0.18) | +3.52 / +1.66 (0.25) |
| 2021 | +2.02 / +3.10 (0.14) | +1.90 / +2.47 (0.13) | +1.80 / +3.01 (0.31) |
| 2022 | +2.38 / +3.34 (0.32) | +1.95 / +2.57 (0.23) | +0.34 / +3.54 (0.30) |
| 2023 | +1.83 / +2.94 (0.20) | +2.14 / +2.73 (0.11) | +2.67 / +3.53 (0.34) |
| 2024 | +2.18 / +2.87 (0.14) | +2.11 / +2.96 (0.10) | +3.32 / +0.53 (0.47) |
| 2025 | +1.92 / +3.11 (0.13) | +1.96 / +2.42 (0.17) | +4.00 / +2.17 (0.88) |

Without home internet or benefits, the replication runs 1.07–2.77% below BLS
for renters and 1.41–2.25% below for owners with mortgages in every year, and
owners without mortgages sit above BLS in five of seven years. We estimate that
home internet raises thresholds by 1.53–2.38% for renters, 1.66–2.14% for
owners with mortgages and 0.34–4.00% for owners without mortgages. Internet
enters FCSUti but not SU, so if we held the band fixed, each threshold would
rise by about `0.82 × 1.2` times in-band home internet, and the price factors
with internet's CPI weight would move that rise slightly. The rest comes from
units entering and leaving the band, which moves each tenure's in-band shelter
and utilities. Owners without mortgages hold less than a tenth of the band by
weight, so their threshold's rise varies most across years. With home
internet, renters land between 0.90% below and 1.02% above BLS, owners with
mortgages between 0.19% below and 0.52% above, and owners without mortgages
2.01–4.50% above. In the band with home internet and without benefits, our
home internet runs 1.00–1.04 times BLS's in every year.

The stage then lifts thresholds by 2.87–3.36% for renters, 2.42–2.96% for
owners with mortgages and 0.53–3.54% for owners without, so every tenure lands
above BLS in every year: renters by 2.18–4.40%, owners with mortgages by
2.51–3.10% and owners without mortgages by 4.94–7.06%. The replication's
shelter and utilities hold more than BLS's papers describe, and its other
approximations (its CPI convention, the food allocation, the percentile
convention and sample policies) move levels too. In the [comparison with BLS
components](#comparison-with-bls-components), we split the gap by term and
rerun the replication under BLS's written definitions.

Component lifts, each component alone, in percent of the threshold with home
internet:

| Component | 2022 renter | 2022 with mortgage | 2022 without mortgage | 2025 renter | 2025 with mortgage | 2025 without mortgage |
|---|---:|---:|---:|---:|---:|---:|
| School lunch | +1.02 | +1.15 | +2.45 | +1.51 | +1.32 | +0.02 |
| WIC | +0.02 | +0.04 | +0.17 | +0.00 | +0.00 | +0.00 |
| LIHEAP | +0.10 | −0.01 | +0.14 | +0.02 | +0.02 | −0.11 |
| Broadband | +0.00 | +0.00 | +0.00 | −0.00 | +0.02 | +0.14 |
| Rental assistance | +2.25 | +1.07 | +1.78 | +2.23 | +1.26 | −1.25 |

For renters and owners with mortgages, school lunch and rental assistance
alone add 86–120% of the stage's lift in both years. The components interact
through band composition, so they do not sum to the total: for owners without
mortgages, the two add 119% of the lift in 2022 and −57% in 2025, when rental
assistance alone lowers that threshold by 1.25%.

### Growth, 2022 to 2025

Write `F(d, k, p)` for the threshold from the window of target year `d`,
with home internet and with the stage off (`k = 0`) or on (`k = 1`), in
prices of year `p`. Growth of the full replication factors exactly as

```text
F(2025,1,2025) / F(2022,1,2022) = price × real × in_kind
real    = [F(2025,0,2025) / F(2022,0,2022)] / price
in_kind = [F(2025,1,2025) / F(2025,0,2025)] / [F(2022,1,2022) / F(2022,0,2022)]
```

with `price` either BLS's FCSUti index ratio (146.712 / 128.478, +14.19%)
or the package CPI with home internet, `F(2022,0,2025) /
F(2022,0,2022)`. The in-kind factor does not depend on the price measure.
Additive contributions use the sequential split
`(price − 1) + price × (real − 1) + price × real × (in_kind − 1)`, which
sums to total growth. Real out-of-pocket spending includes home internet.

| Tenure | BLS corrected | Without home internet or benefits → with home internet → with home internet and benefits | Price | Real out-of-pocket | In-kind (implicate SD) |
|---|---:|---:|---:|---:|---:|
| BLS FCSUti index | | | | | |
| Renter | +22.15% | +20.37% → +19.82% → +19.55% | 14.19 | 5.63 | −0.27 (0.41) |
| Owner with mortgage | +21.61% | +21.15% → +21.15% → +20.98% | 14.19 | 6.96 | −0.17 (0.31) |
| Owner without mortgage | +20.63% | +18.79% → +23.12% → +21.49% | 14.19 | 8.93 | −1.63 (1.13) |
| Package composite CPI | | | | | |
| Renter | | | 12.99 | 6.84 | −0.27 (0.41) |
| Owner with mortgage | | | 13.09 | 8.07 | −0.17 (0.31) |
| Owner without mortgage | | | 13.27 | 9.85 | −1.63 (1.13) |

Contributions are percentage points of 2022–2025 growth. The implicate
standard deviation pairs implicates by index across the two windows.

CPI-U rose 10.01% over the same span (`cpi_annual.json`, 292.655 to
321.943). BLS's thresholds rose 10.6–12.1 points more than CPI-U. Without
home internet or benefits, the replication reproduces 85% of that excess for
renters, 96% for owners with mortgages and 83% for owners without. With home
internet it reproduces 81%, 96% and 123%, and with home internet and
benefits, 79%, 95% and 108%.

We estimate that home internet changes the replication's 2022–2025 growth by
−0.54 points for renters, +0.01 for owners with mortgages and +4.33 for owners
without mortgages. It adds 0.34% to that last threshold in 2022 and 4.00% in
2025, as units enter and leave the band. In-kind benefits then change growth by
−0.3 points for renters, −0.2 for owners with mortgages and −1.6 for owners
without mortgages. Each in-kind change lies within one standard error of zero
with sampling and imputation uncertainty combined ([standard errors of
growth](#growth-from-2022-to-2025)). The lift itself moved little for
renters and owners with mortgages, from 3.34% to 3.11% and from 2.57% to 2.42%,
and fell from 3.54% to 2.17% for owners without mortgages. Mean imputed amounts
across the estimation sample rose 20% in threshold-year dollars (\$954 to
\$1,148), in line with the 20–23% growth of the thresholds with home internet.
Within the band that sets the thresholds, they rose 14%. Real
out-of-pocket spending in the CE, not in-kind benefits, carries the
replication's growth beyond prices. With home internet, renters' growth trails
BLS's by 2.32 points, and the stage widens that shortfall to 2.59. BLS's imputed
amounts rise faster than ours, and while we hold each band fixed, that
difference accounts for 1.49 of those 2.59 points ([comparison with
BLS components](#comparison-with-bls-components)). The package CPI rises
0.9–1.2 points less than BLS's FCSUti index, so with the package CPI those
points move from prices to real spending. We hold thresholds fixed for this
decomposition; when we rerun the replication with BLS's index as the deflator,
the thresholds themselves change.

### Year over year

In-kind contribution to each year's growth, in percentage points, with
the between-implicate standard deviation:

| Years | Renter | Owner with mortgage | Owner without mortgage |
|---|---:|---:|---:|
| 2019–2020 | +0.12 (0.15) | +0.19 (0.12) | −0.76 (0.33) |
| 2020–2021 | −0.25 (0.12) | −0.27 (0.07) | +1.36 (0.34) |
| 2021–2022 | +0.26 (0.20) | +0.11 (0.14) | +0.56 (0.59) |
| 2022–2023 | −0.43 (0.42) | +0.16 (0.24) | −0.02 (0.40) |
| 2023–2024 | −0.07 (0.20) | +0.24 (0.12) | −3.15 (0.42) |
| 2024–2025 | +0.25 (0.16) | −0.55 (0.17) | +1.70 (0.90) |

The in-kind contribution to each year's growth runs from −3.1 to +1.7 points.
Owners without mortgages swing most and carry the largest implicate spread in
every pair of years but 2022–2023. They hold less than a tenth of the band
by weight (7.4% in 2025), so a few units entering or leaving the band
move their mean. Each window shares four of its five reference years with the
next. None of these contributions reaches two standard errors once we combine
sampling and imputation uncertainty ([standard errors by
year](#yearly-growth)).

### Deflating with BLS's FCSUti index

The replication carries each unit's spending to threshold-year dollars
with a composite of CPI-U series (food, apparel, shelter, fuels and
utilities, and telephone services, plus internet services in the runs on
this page), weighted by the window's CE spending and applied by collection
year. BLS deflates with its FCSUti index, which it builds from CPI basic
item-area indexes. Its 2025 average imputes October, which BLS did not
collect ([BLS 2025 thresholds](https://www.bls.gov/pir/spm/spm_thresholds_2025.htm)).
A sensitivity run replaces every component series, internet included, with
BLS's published FCSUti levels ([BLS
table](https://www.bls.gov/pir/spm/spm_chart_2025data.htm)), so each unit's
price factor becomes `I(T) / I(c)` for collection year `c`; the script checks
that factor for every collection year.

2022–2025 growth without home internet or benefits → with home internet →
with home internet and benefits:

| Tenure | BLS corrected | Package CPI | FCSUti index |
|---|---:|---:|---:|
| Renter | +22.15% | +20.37% → +19.82% → +19.55% | +21.48% → +21.11% → +20.69% |
| Owner with mortgage | +21.61% | +21.15% → +21.15% → +20.98% | +22.08% → +22.13% → +22.23% |
| Owner without mortgage | +20.63% | +18.79% → +23.12% → +21.49% | +20.81% → +22.99% → +21.84% |

Without home internet or benefits, deflating with BLS's index brings the
replication's growth within 0.7 points of BLS's for every tenure (−0.67, +0.47
and +0.18 points). With home internet, deflating with BLS's index instead of
the package CPI raises growth by 1.3 points for renters and 1.0 for owners with
mortgages and lowers it by 0.1 for owners without mortgages. The replication's
growth then trails BLS's by 1.03 points for renters and exceeds it by 0.51 for
owners with mortgages and 2.36 for owners without, and it reproduces 91%, 104%
and 122% of BLS's growth above CPI-U. With the stage, renters fall 1.46 points
short, and owners run 0.61 and 1.21 points ahead.

The stage's change in 2022–2025 growth with each deflator, in percentage
points, with the between-implicate standard deviation:

| Tenure | Package CPI | FCSUti index |
|---|---:|---:|
| Renter | −0.27 (0.41) | −0.42 (0.39) |
| Owner with mortgage | −0.17 (0.31) | +0.10 (0.35) |
| Owner without mortgage | −1.63 (1.13) | −1.15 (0.79) |

Owners without mortgages' change reaches 1.4 times the implicates' spread with
either deflator, and renters' reaches 1.1 times with BLS's index; the other
changes stay within it. With sampling and imputation uncertainty combined, all
six lie within one standard error of zero ([standard errors of
growth](#growth-from-2022-to-2025)).

Signed gap from BLS's corrected thresholds in percent with FCSUti
deflation, without home internet or benefits → with home internet → with
home internet and benefits:

| Target | Renter | Owner with mortgage | Owner without mortgage |
|---|---:|---:|---:|
| 2019 | −0.76 → +0.80 → +4.09 | −1.35 → +0.39 → +2.94 | −0.54 → +2.84 → +5.67 |
| 2020 | −1.16 → +0.61 → +3.79 | −1.31 → +0.47 → +3.32 | +0.23 → +3.65 → +5.62 |
| 2021 | −1.34 → +0.66 → +3.80 | −1.55 → +0.53 → +2.82 | +0.48 → +2.58 → +5.98 |
| 2022 | −1.63 → +0.72 → +4.23 | −1.67 → +0.36 → +2.86 | +1.00 → +2.59 → +5.51 |
| 2023 | −1.10 → +0.91 → +3.86 | −2.10 → +0.09 → +2.90 | +0.65 → +3.50 → +7.04 |
| 2024 | −0.96 → +1.19 → +4.06 | −1.99 → +0.20 → +3.23 | +1.29 → +5.18 → +5.60 |
| 2025 | −2.16 → −0.14 → +2.99 | −1.29 → +0.78 → +3.38 | +1.15 → +4.60 → +6.57 |

With home internet, out-of-pocket levels move by −0.30% to +0.77% against the
package-CPI run, and the stage carries every tenure above BLS in every year.
The run shows how much the deflator matters, not how BLS deflates: it keeps the
replication's annual price factors by collection year.

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
adults and two children. Unless a table says otherwise, ours include home
internet and the stage and use the package CPI.

### Imputed amounts in the band

Mean per consumer unit in the 47th–53rd percentile band, our estimate / BLS's.
Rental assistance averages over all renters in the band, assisted or not.

| Target | All imputed benefits | Rental assistance per renter | School lunch |
|---|---:|---:|---:|
| 2019 | \$917 / \$705 | \$1,189 / \$630 | \$314 / \$371 |
| 2020 | \$911 / \$742 | \$1,172 / \$633 | \$332 / \$402 |
| 2021 | \$903 / \$764 | \$1,238 / \$712 | \$327 / \$407 |
| 2022 | \$1,028 / \$855 | \$1,351 / \$738 | \$413 / \$500 |
| 2023 | \$1,014 / \$927 | \$1,236 / \$772 | \$476 / \$596 |
| 2024 | \$1,063 / \$1,049 | \$1,277 / \$940 | \$513 / \$664 |
| 2025 | \$1,170 / \$1,257 | \$1,448 / \$1,243 | \$563 / \$742 |

We estimate that our rental assistance per renter exceeds BLS's by 17–89% in
every year, and that our school lunch trails BLS's by 15–24%. Our estimated
total exceeds BLS's by 9–30% through 2023 and by 1% in 2024, then trails it by
7% in 2025. Between-implicate standard deviations reach \$187 for rental
assistance per renter and \$22 for school lunch.

Each tenure's share of the band in percent, ours / BLS's:

| Target | Renter | Owner with mortgage | Owner without mortgage |
|---|---:|---:|---:|
| 2019 | 44.8 / 43.4 | 47.6 / 47.4 | 7.6 / 9.2 |
| 2020 | 43.9 / 44.3 | 48.2 / 46.8 | 7.9 / 8.9 |
| 2021 | 42.5 / 43.1 | 49.5 / 48.1 | 7.9 / 8.8 |
| 2022 | 42.3 / 41.5 | 49.4 / 50.3 | 8.2 / 8.1 |
| 2023 | 40.0 / 38.1 | 51.9 / 52.0 | 8.0 / 9.9 |
| 2024 | 40.0 / 37.2 | 51.9 / 52.7 | 8.1 / 10.0 |
| 2025 | 39.5 / 38.7 | 53.2 / 51.0 | 7.4 / 10.2 |

Our band's share of owners without mortgages trails BLS's in every year but
2022, by up to 2.9 points.

### The level gap, term by term

Each term's part of the gap in percentage points of BLS's threshold, lowest to
highest over 2019–2025, with Other spread:

| Term | Renter | Owner with mortgage | Owner without mortgage |
|---|---:|---:|---:|
| Imputed benefits | +0.05 to +1.58 | −0.38 to −0.02 | −0.57 to −0.04 |
| Shelter | +2.46 to +4.07 | +2.47 to +3.50 | +4.89 to +8.13 |
| Home internet | −0.02 to +0.07 | −0.02 to +0.07 | −0.03 to +0.08 |
| Utilities | −0.33 to +0.24 | +0.05 to +0.47 | −0.57 to +0.71 |
| Food | −0.23 to +0.48 | −0.23 to +0.48 | −0.28 to +0.57 |
| Clothing | −0.89 to −0.23 | −0.89 to −0.23 | −1.05 to −0.28 |
| Telephone | −0.09 to +0.23 | −0.09 to +0.23 | −0.10 to +0.28 |

We estimate that our shelter term adds 2.46–8.13 points in every tenure and
year and supplies at least 60% of each gap. Imputed benefits lower owners' gaps
in every year, because our school lunch trails BLS's, and add 0.05–1.58 points to
the renter gap, because our rental assistance per renter exceeds BLS's. Our
clothing term trails BLS's by 0.23–1.05 points, and food, telephone and
utilities stay within 0.72 points. For BLS's home internet, we use the
workbook's internet row with equal dollars across tenures, since that row
balances the second identity, and subtract the band's mean broadband subsidy.
Ours is the band's mean UCC 690114 spending, 0.99–1.03 times BLS's, so the home
internet term stays within 0.08 points of BLS's. Under Other separate,
broadband takes each tenure's own mean, and each side's home internet term
takes the tenure's broadband difference from the band mean, a few dollars,
so the terms still sum to the threshold. Our home internet term supplies
1.78–2.44% of our thresholds with Other spread and 1.49–2.04% with Other
separate; BLS's supplies 1.85–2.55% and 1.54–2.12% of its thresholds.

With Other separate, the food, clothing, telephone, school lunch and WIC
terms fall by a sixth, as does the sum of the home internet and broadband
terms. The shelter, utilities, rental assistance and LIHEAP terms lose their
parts of `0.2 × F`, and the Other term gathers all those parts, adding
0.51–0.75 points to the gap:

| Term | Renter | Owner with mortgage | Owner without mortgage |
|---|---:|---:|---:|
| Imputed benefits | +0.08 to +1.46 | −0.35 to −0.14 | −0.53 to −0.18 |
| Shelter | +1.84 to +3.36 | +1.95 to +2.79 | +4.34 to +7.38 |
| Home internet | −0.02 to +0.05 | −0.02 to +0.06 | −0.02 to +0.07 |
| Utilities | −0.30 to +0.20 | +0.09 to +0.43 | −0.54 to +0.65 |
| Food | −0.19 to +0.40 | −0.20 to +0.40 | −0.24 to +0.48 |
| Clothing | −0.74 to −0.19 | −0.74 to −0.19 | −0.88 to −0.23 |
| Telephone | −0.07 to +0.19 | −0.07 to +0.19 | −0.09 to +0.23 |
| Other (0.2 × FCSUti) | +0.51 to +0.63 | +0.52 to +0.63 | +0.62 to +0.75 |

We estimate that our shelter term then adds 1.84–7.38 points, and imputed
benefits add 0.08–1.46 points to the renter gap.

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
papers leave out in parentheses, and in-band home internet per unit, ours /
BLS's:

| Target | Renter | Owner with mortgage | Owner without mortgage | Home internet, ours / BLS |
|---|---:|---:|---:|---:|
| 2019 | \$773 (\$440) | \$851 (\$318) | \$1,504 (\$1,055) | \$543 / \$547 |
| 2020 | \$783 (\$479) | \$988 (\$347) | \$1,418 (\$1,252) | \$612 / \$598 |
| 2021 | \$849 (\$463) | \$866 (\$327) | \$1,905 (\$1,054) | \$649 / \$656 |
| 2022 | \$908 (\$431) | \$914 (\$392) | \$1,505 (\$867) | \$738 / \$718 |
| 2023 | \$959 (\$407) | \$879 (\$475) | \$2,306 (\$834) | \$812 / \$787 |
| 2024 | \$1,609 (\$419) | \$1,337 (\$496) | \$2,282 (\$1,219) | \$858 / \$852 |
| 2025 | \$935 (\$423) | \$1,337 (\$548) | \$3,088 (\$1,623) | \$869 / \$878 |

Other lodging, vacation-home principal and rent as pay make up 26–88% of the
shelter excess, and other lodging alone 16–86%. Meals as pay add \$17–\$31 to
in-band food. In the band with home internet and benefits, our home internet
runs within 3.2% of BLS's in every year.

`apply_bls_paper_definition` removes those four amounts and vacation-home
utilities from the raw FMLI columns before the replication adds home internet
and builds its CPI weights, price factors and bands. FMLI summarizes utilities for owned vacation
homes in `UTILOWN` and for rented ones in `UTILRNT`, so the function removes
both from owners' utilities and only `UTILRNT` from renters'. Those summaries
leave out coal, wood and other fuels for vacation homes (UCCs 250913 and
250914), so those fuels stay in `UTIL`. In our band, we estimate that the
removed vacation-home utilities average \$6–\$79 per owner without a mortgage,
\$7–\$19 per owner with one and \$0–\$4 per renter.

Signed gap from BLS's corrected thresholds in percent under these definitions,
with home internet, without → with the stage:

| Target | Renter | Owner with mortgage | Owner without mortgage |
|---|---:|---:|---:|
| 2019 | −1.28 → +1.63 | −1.71 → +0.82 | −0.69 → +2.40 |
| 2020 | −1.42 → +1.44 | −1.53 → +0.90 | −0.59 → +3.02 |
| 2021 | −0.94 → +1.90 | −1.20 → +0.99 | −0.19 → +2.35 |
| 2022 | −0.40 → +2.64 | −1.18 → +1.36 | −1.10 → +2.75 |
| 2023 | −0.82 → +2.11 | −1.66 → +1.08 | +0.13 → +3.63 |
| 2024 | −0.77 → +2.10 | −1.86 → +0.76 | −0.81 → +2.34 |
| 2025 | −2.13 → +0.85 | −2.09 → +0.77 | +0.90 → +1.05 |

With BLS's FCSUti index as the deflator:

| Target | Renter | Owner with mortgage | Owner without mortgage |
|---|---:|---:|---:|
| 2019 | −0.83 → +2.12 | −1.15 → +1.35 | −0.30 → +3.02 |
| 2020 | −0.94 → +1.97 | −1.03 → +1.31 | −0.30 → +3.32 |
| 2021 | −0.82 → +1.94 | −1.09 → +1.12 | −0.39 → +2.67 |
| 2022 | −0.73 → +2.46 | −1.35 → +1.08 | −0.79 → +2.65 |
| 2023 | −0.76 → +2.34 | −1.49 → +1.18 | +0.28 → +3.35 |
| 2024 | −0.14 → +2.58 | −1.52 → +1.31 | −0.18 → +2.74 |
| 2025 | −1.60 → +1.51 | −1.31 → +1.54 | +1.54 → +2.21 |

Under these definitions, the replication with home internet and without the
stage trails BLS in 19 of the 21 tenure-years, by up to 2.13% with the package
CPI, and runs above it for owners without mortgages in 2023 and 2025. Imputed
benefits lift all 21 above BLS, 6 of them by less than 1%, and raise the mean
absolute gap from 1.11 to 1.76%. Under the replication's own definitions, they
raise it from 1.35 to 3.99%, and with BLS's index and these definitions, from
0.88 to 2.08%.

Each term's part of the gap under these definitions, in percentage points of
BLS's threshold, with Other spread:

| Term | Renter | Owner with mortgage | Owner without mortgage |
|---|---:|---:|---:|
| Imputed benefits | −0.24 to +1.36 | −0.43 to −0.02 | −0.63 to −0.04 |
| Shelter | +1.00 to +2.56 | +1.00 to +1.85 | +2.70 to +4.46 |
| Home internet | −0.04 to +0.05 | −0.04 to +0.05 | −0.05 to +0.06 |
| Utilities | −0.33 to +0.18 | −0.11 to +0.23 | −0.91 to +0.07 |
| Food | −0.41 to +0.50 | −0.41 to +0.50 | −0.50 to +0.60 |
| Clothing | −0.93 to −0.11 | −0.92 to −0.11 | −1.09 to −0.13 |
| Telephone | −0.08 to +0.32 | −0.08 to +0.33 | −0.10 to +0.39 |

When we adopt these definitions, we estimate 21–62% less in the shelter term,
44% less on average, and the shelter term still adds 1.00–4.46 points. We have
not traced the remaining shelter excess.

The same terms with Other separate:

| Term | Renter | Owner with mortgage | Owner without mortgage |
|---|---:|---:|---:|
| Imputed benefits | −0.19 to +1.26 | −0.37 to −0.12 | −0.57 to −0.16 |
| Shelter | +0.75 to +2.15 | +0.75 to +1.49 | +2.42 to +4.02 |
| Home internet | −0.03 to +0.04 | −0.03 to +0.05 | −0.04 to +0.06 |
| Utilities | −0.28 to +0.15 | −0.05 to +0.21 | −0.90 to +0.06 |
| Food | −0.34 to +0.42 | −0.34 to +0.42 | −0.42 to +0.50 |
| Clothing | −0.77 to −0.09 | −0.77 to −0.09 | −0.91 to −0.11 |
| Telephone | −0.07 to +0.27 | −0.07 to +0.27 | −0.08 to +0.32 |
| Other (0.2 × FCSUti) | +0.20 to +0.35 | +0.20 to +0.35 | +0.24 to +0.42 |

### Imputed amounts and threshold growth

In-band amounts, 2022 to 2025:

| Series | All imputed benefits | Rental assistance per renter | School lunch |
|---|---:|---:|---:|
| BLS | \$855 → \$1,257 (+\$401) | \$738 → \$1,243 (+\$505) | \$500 → \$742 (+\$242) |
| Ours, package CPI | \$1,028 → \$1,170 (+\$143) | \$1,351 → \$1,448 (+\$97) | \$413 → \$563 (+\$150) |
| Ours, FCSUti index | \$1,020 → \$1,178 (+\$158) | \$1,347 → \$1,484 (+\$137) | \$411 → \$566 (+\$154) |

BLS's imputed benefits rise \$401 and ours \$143 with the package CPI, and
BLS's rise exceeds all five of our implicates' with either deflator
(\$24–\$312). Across all units in the band, rental assistance supplies \$175 of
that difference and school lunch \$92. From the 2019 to the 2022 thresholds,
BLS's rental assistance per renter rose 17%, and we estimate that ours rose 14%.
For the 2019–2023 thresholds, we estimate rental assistance per renter 60 to 89%
above BLS's, \$1,351 against \$738 in 2022. From 2022 to 2025, BLS's amount
rose by \$505, and we estimate that ours rose by \$97, with a standard error of
\$453 ([Rises in imputed
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
| Ours, package CPI | 1.5 / 2.3 / 2.6 | 1.4 / 2.1 / 2.4 | −0.32 / +0.09 / +0.10 | 19.87 / 20.89 / 21.39 |
| Ours, FCSUti index | 2.4 / 2.3 / 2.6 | 2.3 / 2.0 / 2.3 | −0.25 / +0.10 / +0.10 | 20.94 / 22.13 / 21.74 |

Threshold growth with the stage less BLS's, in percentage points, with imputed
terms kept → removed from both series:

| Tenure | Replication's definitions, package CPI | Replication's definitions, FCSUti index | BLS's written definitions, package CPI | BLS's written definitions, FCSUti index |
|---|---:|---:|---:|---:|
| Renter | −2.59 → −1.10 | −1.46 → −0.03 | −2.13 → −0.54 | −1.13 → +0.32 |
| Owner with mortgage | −0.63 → −0.35 | +0.61 → +0.90 | −0.70 → −0.40 | +0.56 → +0.83 |
| Owner without mortgage | +0.86 → +1.36 | +1.21 → +1.71 | −2.00 → −1.54 | −0.52 → −0.08 |

Removing imputed terms from both series narrows the renter shortfall from −2.59
to −1.10 points with the package CPI and closes it with BLS's index (−1.46 to
−0.03). Owners' figures move by 0.28–0.50 points. Those renter figures with
imputed terms removed carry between-implicate standard deviations of 0.57–0.64
points. BLS's thresholds draw on the same CE interviews as ours, so the
[standard errors of growth](#growth-from-2022-to-2025) do not measure how much
of these gaps sampling could explain.

Holding each band fixed leaves out rank shifts. The stage also reorders
units, which moves the replication's 2022–2025 growth by a further +0.04 points
for renters, −0.27 for owners with mortgages and −1.72 for owners without
mortgages. BLS publishes no unit-level values, so we can't measure its rank
shifts.

2022–2025 growth with the stage, under each definition and deflator:

| Tenure | BLS corrected | Replication's definitions, package CPI | Replication's definitions, FCSUti index | BLS's written definitions, package CPI | BLS's written definitions, FCSUti index |
|---|---:|---:|---:|---:|---:|
| Renter | +22.15% | +19.55% | +20.69% | +20.02% | +21.01% |
| Owner with mortgage | +21.61% | +20.98% | +22.23% | +20.91% | +22.17% |
| Owner without mortgage | +20.63% | +21.49% | +21.84% | +18.63% | +20.12% |

Using BLS's written definitions and BLS's index, we estimate 2022–2025 growth
with home internet and the stage within 1.2 points of BLS's for every tenure.

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
windows use interviews from 2014Q2 through 2025Q1, all from the 2014–2024
releases, so we set `k = 0`. In each of those quarters, every record carries 22
positive replicate weights and 22 blank ones, and
`scripts/estimate_ce_replicate_uncertainty.py` stops if any record carries a
different number of positive weights.

We rerun the whole replication, home internet included, under each
replicate's weights. Consumer units with a zero weight drop out, and we
recompute the package CPI's component weights (internet's among them), the
47th–53rd percentile band and the band means with the replicate's weights.
Without the stage, each run includes home internet and no benefits; with it, we
add each implicate's imputed amounts to the same units before we select the
band. Each record keeps its replicate weights in
every window that holds it, so the standard errors of growth account for the
quarters two windows share, eight between the 2022 and 2025 windows.

We keep each implicate's imputed amounts from the full-sample run in every
replicate. We fit the CPS ASEC participation and amount models and the CE rent
model once, with full-sample weights. For each implicate, we draw the models'
parameters from their estimated sampling distributions, so the spread across
implicates carries part of the models' estimation uncertainty. We estimate
those distributions as if units were independent, so they leave out the CPS
ASEC's and the CE's strata and clusters. The CE income behind each unit's
poverty ratio, `FINCBTXM`, averages BLS's five income imputations, so our
standard errors leave out their spread as well. In the FCSUti run, we take every price factor from
BLS's published index, so the factors stay the same in every replicate.

From one quarter to the next, every consumer unit interviewed in both keeps its
pattern of positive and blank replicate weights, except across two pairs of
quarters. Of the units interviewed in both 2015Q1 and 2015Q2, 1.9% of 2,644 keep
it, and of those interviewed in both 2016Q4 and 2017Q1, 3.4% of 3,979 do. For
a unit whose pattern changed, its interviews before and after the change can
fall in different half samples under one replicate number, so the replicates can
miss part of the correlation between those interviews. The 2019 window spans
both changes, the 2020 and 2021 windows span the 2016Q4–2017Q1 change, and the
2022–2025 windows span neither.

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
| 2019 | 213 / 240 / 204 | 192 / 202 / 201 | 300 / 387 / 328 |
| 2020 | 226 / 225 / 257 | 252 / 249 / 224 | 312 / 406 / 334 |
| 2021 | 234 / 227 / 242 | 270 / 267 / 286 | 379 / 492 / 259 |
| 2022 | 264 / 283 / 308 | 282 / 311 / 319 | 585 / 640 / 439 |
| 2023 | 214 / 232 / 345 | 343 / 328 / 330 | 732 / 714 / 517 |
| 2024 | 221 / 245 / 325 | 347 / 348 / 303 | 820 / 694 / 682 |
| 2025 | 379 / 299 / 393 | 414 / 418 / 327 | 519 / 796 / 560 |

With the stage, our standard errors run 0.67–1.18 times BLS's published ones
for renters, 0.93–1.28 times for owners with mortgages and 1.02–1.90 times for
owners without mortgages. Deflating with BLS's index instead moves each end of
those ranges by 0.06 or less. Our standard errors equal 0.60–0.99% of the
threshold for renters and owners with mortgages and 1.50–2.18% for owners
without mortgages, who hold less than a tenth of the band by weight.
Sampling supplies at least 80% of each level's variance, and
the degrees of freedom range from 25 to 41. BLS publishes a standard error for
each threshold in its workbooks. Garner (2010) computed the standard errors
of BLS's 2006–2008 experimental thresholds by balanced repeated replication
with the CE's 44 replicate weights
([BLS Working Paper 436](https://www.bls.gov/osmr/research-papers/2010/pdf/ec100040.pdf)),
as we do, and Garner and Gudrais (2018) base theirs on the same 44
replicates. BLS's methods page and workbooks do not say how its current
replicates treat the percentile band or the imputed benefits. Its
thresholds draw on the same CE interviews as ours, so these standard errors do
not measure how much sampling could explain of any gap between our thresholds
and BLS's.

### Growth from 2022 to 2025

2022–2025 growth, with standard errors in parentheses. The degrees of freedom
apply to the stage's change, and in the last column we remove the imputed terms
from both thresholds, as in the
[comparison with BLS components](#imputed-amounts-and-threshold-growth):

| Tenure | Without the stage | With the stage | Stage's change, points | Degrees of freedom | Imputed terms removed |
|---|---:|---:|---:|---:|---:|
| Package composite CPI |  |  |  |  |  |
| Renter | +19.82% (1.03) | +19.55% (1.02) | −0.27 (0.83) | 18 | +19.87% (1.30) |
| Owner with mortgage | +21.15% (0.90) | +20.98% (1.05) | −0.17 (0.68) | 21 | +20.89% (1.08) |
| Owner without mortgage | +23.12% (2.92) | +21.49% (3.15) | −1.63 (3.19) | 29 | +21.39% (3.20) |
| BLS's FCSUti index |  |  |  |  |  |
| Renter | +21.11% (0.99) | +20.69% (1.00) | −0.42 (0.82) | 19 | +20.94% (1.33) |
| Owner with mortgage | +22.13% (0.90) | +22.23% (1.02) | +0.10 (0.69) | 17 | +22.13% (1.06) |
| Owner without mortgage | +22.99% (2.71) | +21.84% (2.86) | −1.15 (3.00) | 35 | +21.74% (2.93) |

The stage's change in 2022–2025 growth lies within one standard error of zero in
every tenure with either deflator. Renters' −0.42 points with BLS's index
comes closest to that bound, at 0.52 standard errors. With the package CPI, 95% intervals
for the change run from −2.03 to +1.48 points for renters, −1.59 to +1.24 for
owners with mortgages and −8.15 to +4.89 for owners without. With either
deflator, the implicates' spread supplies 8–30% of each change's variance, and
the degrees of freedom fall to 17–35. Across both deflators, growth with and
without the stage carries standard errors of 0.90–1.05 points for renters and owners with mortgages and 2.71–3.15 for
owners without mortgages.

### Yearly growth

The stage's change in each year's growth with the package CPI, in percentage
points, with standard errors:

| Years | Renter | Owner with mortgage | Owner without mortgage |
|---|---:|---:|---:|
| 2019–2020 | +0.12 (0.39) | +0.19 (0.29) | −0.76 (1.14) |
| 2020–2021 | −0.25 (0.41) | −0.27 (0.34) | +1.36 (1.29) |
| 2021–2022 | +0.26 (0.46) | +0.11 (0.42) | +0.56 (1.89) |
| 2022–2023 | −0.43 (0.64) | +0.16 (0.47) | −0.02 (1.82) |
| 2023–2024 | −0.07 (0.49) | +0.24 (0.44) | −3.15 (2.02) |
| 2024–2025 | +0.25 (0.67) | −0.55 (0.51) | +1.70 (2.89) |

No yearly change reaches two standard errors with either deflator: the largest,
owners without mortgages' change from 2023 to 2024, reaches 1.56 with the
package CPI and 1.52 with BLS's index. With the package CPI, each year's growth
with and without the stage carries standard errors of 0.38–0.70 points for renters and owners with
mortgages and 1.09–2.18 for owners without mortgages. For example, renter growth
from 2024 to 2025 runs 4.83% with the stage and 4.58% without it, with standard
errors of 0.55 and 0.67 points.

### Rises in imputed amounts

The 2022–2025 rise in mean in-band amounts, BLS's beside ours with standard
errors:

| Amount | BLS | Package composite CPI | BLS's FCSUti index |
|---|---:|---:|---:|
| All imputed benefits | +\$401 | +\$143 (190) | +\$158 (187) |
| Rental assistance per renter | +\$505 | +\$97 (453) | +\$137 (436) |
| School lunch | +\$242 | +\$150 (47) | +\$154 (45) |

With the package CPI, our in-band amounts carry standard errors of \$73–\$121 a
year for all imputed benefits, \$155–\$321 for rental assistance per renter and
\$16–\$35 for school lunch. The two windows' band amounts move together only
weakly: within each implicate and under either deflator, their replicate
deviations correlate at −0.20 to +0.40, so each rise's standard error exceeds
both years'. With either deflator, the implicates' spread supplies 46–55% of
each rise's variance.

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
- Home internet is UCC 690114 alone, priced with CUUR0000SEEE03. BLS has
  not published the UCCs or the price series behind its home internet term.
- The package's archived replication excludes home internet, and the
  canonical forecast, nowcast and projections exclude it until we next
  rebuild the forecast.
- BLS applies an annual-average FCSUti CPI-U to quarterly CE data and does
  not say which year's average each quarter gets. The runs use the average
  for each interview's collection year.
- From reference year 2020, the year of the statutory deadline, we add no
  WIC in any state, even where the middle of a unit's reference period falls
  before the deadline. Six states finished during 2020 before the deadline,
  and FNS dates six others and DC after it. With each state's own date, we
  estimate that the 2021–2025 thresholds move by −\$5 to +\$18.
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
unchanged. Before the stage runs, `spm_calculator.ce_internet.add_home_internet`
adds home internet to the run.

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
from spm_calculator.ce_internet import (
    INTERNET_COLUMN,
    add_home_internet,
    read_internet_costs,
    with_internet_cpi,
)

# Each FMLI quarter gets its units' UCC 690114 costs before the window
# is assembled: frame[INTERNET_COLUMN] = read_internet_costs(frame).
cpi = with_internet_cpi(cpi)
run = prepare_out_of_pocket(
    ce_window, 2025, youth_policy="exclude_unresolved", cpi_series=cpi
)
run = add_home_internet(run, cpi)
imputation = impute_in_kind(ce_units, cps_donors, InKindConfig(implicates=5))
result = replicate_with_in_kind(run, imputation.for_target(0, 2025))
result["thresholds"], result["out_of_pocket"]["thresholds"]
result["without_home_internet"]["thresholds"]
```

`result["out_of_pocket"]` holds the thresholds with home internet and no
benefits, and `result["without_home_internet"]` the package's thresholds
without home internet or benefits.

`scripts/replicate_ce_inkind.py` builds `ce_units` and `cps_donors` from
cached CE Interview bundles (2014–2024) and CPS ASEC public-use files
(2015–2025), runs 2019–2025 with and without the stage, repeats both with
BLS's FCSUti index as the deflator, and writes
`spm_calculator/data/current/ce_inkind_replication_2019_2025.json`. It
reads home internet from the MTBI files in the same bundles and makes no
network requests. It stops with an error unless the out-of-pocket run
without home internet matches the archived receipt exactly and an all-zero
in-kind table reproduces the run with home internet exactly.

### Receipt keys

In the replication and components receipts, each target year holds one
record per run. The replication receipt also records each run's gap to BLS's
corrected thresholds in each year's `results` entry, and its growth in each
year pair's `decompositions` entry (such as `2022-2025`) and that entry's
`fcsuti_deflated`:

| Run | Year record | Gap | Growth |
|---|---|---|---|
| Without home internet or benefits | `without_home_internet` | `gap_percent_without_home_internet` | `growth_percent_without_home_internet` |
| With home internet | `without_in_kind` | `gap_percent_without` | `growth_percent_without` |
| With home internet and benefits | `with_in_kind` | `gap_percent_with` | `growth_percent_with` |

The replication receipt's `stage_effects` holds each step's effect:
`home_internet_dollars` and `home_internet_percent` from the first run to the
second, and `in_kind_dollars` and `in_kind_percent` from the second to the
third. The components receipt's `home_internet` record sets our home internet
term beside BLS's under each accounting, in the band with home internet and
benefits. The replicate receipt reports `without_in_kind` and `with_in_kind`
only, both with home internet.

Keys that compare the run with benefits to the run before it measure benefits
against the run with home internet. In the replication receipt, these are
`in_kind_lift_percent` (equal to `stage_effects.in_kind_percent`), the
`in_kind_lift_percent` of each year's `fcsuti_deflated` entry,
`component_lift_percent`, `share_of_gap_closed` and
`in_kind_percentage_points_by_implicate`, plus the `in_kind` entries of
`package_cpi`, `bls_fcsuti_index` and `fcsuti_deflated.decomposition` in each
`decompositions` pair; that pair's `out_of_pocket_total` and
`real_out_of_pocket` include home internet. In the components receipt's
`growth_2022_2025`, they are `growth_without_stage`, `growth_with_stage`,
`stage_change_points`, `stage_change_by_implicate`,
`stage_change_between_implicate_sd` and `other_spread.rank_shift_points`. In
the replicate receipt, they are `in_kind_lift_percent` and
`stage_change_points`. Replication receipts at
schema version 1, components receipts at schema versions 1 and 2, and
replicate receipts at schema version 1 whose `inputs` have no `internet_cpi`
use `without_in_kind` for the run without home internet or benefits and
`with_in_kind` for the run with benefits and without home internet, and the
same keys compare those two runs.

## Forecast windows: a proposed design

The stage covers observed windows only. The
[rolling forecasts](rolling-forecasts.md) project a future window by
copying same-season donor quarters, keeping each donor's `NEWID`, and
scaling monetary columns, then anchor national levels as
`published_2025 × replication_T / replication_2025`. A follow-up could
carry the stage into those windows:

1. Impute the window's observed quarters with the latest CPS ASEC
   donors. Projected copies keep their donor's `NEWID`, which the
   imputation requires to be unique, and the stage gives every row that
   shares a `NEWID` that unit's amounts.
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

Nothing in the canonical forecast uses the stage. The canonical forecast,
nowcast and projections also exclude home internet until we next rebuild the
forecast; a rebuild that adds it would read UCC 690114 for each donor quarter
and price it with CUUR0000SEEE03.

## Files

- `spm_calculator/ce_inkind.py`: the imputation.
- `spm_calculator/ce_inkind_stage.py`: the stage that adds a table of
  amounts to the CE frame and re-estimates thresholds.
- `spm_calculator/ce_internet.py`: home internet from MTBI UCC 690114 and
  its place in the FCSUti composite CPI.
- `scripts/fetch_internet_cpi.py` and
  `spm_calculator/data/bls/cpi_internet_receipt.json`: the CPI-U internet
  series and BLS's API responses.
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
