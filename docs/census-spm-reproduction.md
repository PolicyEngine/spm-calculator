# Reproducing Census's 2025 SPM estimates

This note opens a step-by-step comparison of PolicyEngine's Supplemental
Poverty Measure (SPM) estimates with the Census Bureau's. PolicyEngine
computes SPM poverty from its own tax and benefit rules, on microdata that
Microcosm imputes and calibrates. A comparison of PolicyEngine's final rate
with Census's would mix all of those differences together. This series
separates them: it starts from Census's published estimates, rebuilt from
the public-use survey file, and then swaps in PolicyEngine's pieces one at
a time, so that each piece's effect shows on its own. The
[series plan](spm-evidence-series.md) sets out the later steps.

This first step rebuilds the SPM estimates in Census's report for 2025 from
the public-use file of the survey behind them, using only the file's own
SPM fields and replicate weights.

## Summary

<!-- BEGIN GENERATED: headline -->
- **SPM rate.** We estimate that 13.11 percent of people lived in SPM poverty in 2025, with a 90 percent margin of error of 0.31 points. Census publishes 13.11 ± 0.31. Across all people and the three age groups, 5 of the 8 published rates and margins match to the published two decimals, and none differs by more than 0.01 points.
- **Element effects.** 33 of the 76 published effects of single resource elements match to two decimals. The largest gap is 0.06 points, in two cells: Child Tax Credit (refundable portion), under 18 years; Federal income tax, under 18 years. For all 76 effects, the gap is smaller than Census's published margin of error, and no margin of error differs by more than 0.01 points.
- **Characteristics.** For all 45 Table 4 rows that the public-use file can define, our poverty rate and number in poverty fall within Census's published margins of error, and 31 rates match to the published decimal. The four residence rows need geography that the public-use file withholds for some households.
<!-- END GENERATED: headline -->

Every number between the generated-block markers in this note comes from
[`reproduction_2025.json`](../spm_calculator/data/census_spm/reproduction_2025.json),
which [`scripts/reproduce_census_spm.py`](../scripts/reproduce_census_spm.py)
rebuilds from the public-use file. A test fails if the note and the results
file disagree.

## Data

- **Microdata.** The 2026 Current Population Survey Annual Social and
  Economic Supplement (CPS ASEC) public-use CSV release,
  [`asecpub26csv.zip`](https://www2.census.gov/programs-surveys/cps/datasets/2026/march/asecpub26csv.zip).
  The script checks its SHA-256 before reading it. The release's
  [data dictionary](https://www2.census.gov/programs-surveys/cps/datasets/2026/march/asec2026_ddl_pub_full.pdf)
  defines every variable code below.
- **Published estimates.** Tables 4 and 5 of
  [*Poverty in the United States: 2025*](https://www.census.gov/library/publications/2026/demo/p60-290.html)
  (P60-290, September 2026). The package bundles both workbooks in
  `spm_calculator/data/census_spm/p60_290/` with a
  [receipt](../spm_calculator/data/census_spm/p60_290/receipt.json) of their
  URLs, sizes and SHA-256 digests, and the parser refuses a workbook whose
  digest differs from the receipt's.

<!-- BEGIN GENERATED: sample -->
| Records | Count |
| :-- | --: |
| People | 134,729 |
| SPM units | 55,401 |
| Households | 53,344 |
| Tax units | 72,979 |
| Weighted people (thousands) | 338,555 |

Input: `asecpub26csv.zip` (139,103,894 bytes, SHA-256 `fe819d0d2fc4470c282e76c247b8aa8b6054811619730307e9f2fe6186707d93`).
<!-- END GENERATED: sample -->

## Method

### Resources, thresholds and poverty status

Each person record carries the SPM unit's resources (`SPM_RESOURCES`),
poverty threshold (`SPM_POVTHRESHOLD`) and poverty status (`SPM_POOR`),
along with the components of resources. A person counts as poor when the
unit's resources fall below its threshold; resources equal to the threshold
do not count. We take resources and thresholds as the file gives them.

The file builds resources from cash income (`SPM_TOTVAL`), plus SNAP
(`SPM_SNAPSUB`), housing subsidies (`SPM_CAPHOUSESUB`), school lunch
(`SPM_SCHLUNCH`), energy assistance (`SPM_ENGVAL`) and WIC (`SPM_WICVAL`),
minus federal income tax after refundable credits (`SPM_FEDTAX`), state
income tax (`SPM_STTAX`), FICA and federal retirement contributions
(`SPM_FICA`), capped work and child care expenses (`SPM_CAPWKCCXPNS`),
medical out-of-pocket expenses and the Medicare Part B subsidy
(`SPM_MEDXPNS`), and child support paid (`SPM_CHILDSUPPD`). The script
checks that identity and the others the reproduction relies on, and stops
if any check in the first table fails:

<!-- BEGIN GENERATED: identities -->
| Check (must be zero) | Result |
| :-- | --: |
| Largest gap between SPM_RESOURCES and its components (dollars) | 0 |
| People whose SPM_POOR differs from resources < threshold | 0 |
| Largest gap between SPM_FEDTAX and SPM_FEDTAXBC - SPM_EITC - SPM_ACTC (dollars) | 0 |
| Largest gap between SPM_TOTVAL and the unit's summed PTOTVAL (dollars) | 0 |
| SPM units whose unit-level fields vary across members | 0 |
| SPM units without exactly one SPM_HEAD | 0 |
| Tax units (TAX_ID) that span two or more SPM units | 0 |
| Largest gap between SPM_EITC and the unit's summed EIT_CRED (dollars) | 0 |
| Largest gap between SPM_ACTC and the unit's summed ACTC_CRD (dollars) | 0 |
| Largest gap between SPM_FEDTAXBC and the unit's summed FEDTAX_BC (dollars) | 0 |
| Largest gap between SPM_FEDTAX and the unit's summed FEDTAX_AC (dollars) | 0 |
| Largest gap between SPM_STTAX and the unit's summed STATETAX_A (dollars) | 0 |
| Largest gap between SPM_FICA and the unit's summed FICA (dollars) | 0 |
| People without replicate weights | 0 |
| People with a negative weight | 0 |

| Check (informational) | Result |
| :-- | --: |
| Largest gap between the replicate file's pwwgt0 and MARSUPWT / 100 (people) | 0.0050 |
| SPM units whose members carry different SPM_FAMTYPE codes | 116 |
| People in those units | 490 |
| People with a negative amount in a published element's field | 0 |
| People with negative state income tax (SPM_STTAX) | 7,368 |
<!-- END GENERATED: identities -->

### Weights and margins of error

Estimates use the person weight `MARSUPWT / 100`. Census bases its published
margins of error on the survey's replicate weights (Table 4, note 2). We
read the 160 replicate weights from `asec_csv_repwgt_2026.csv` (`pwwgt1` to
`pwwgt160`), join them to people by household (`h_seq`) and person number
(`PPPOS`), and compute each estimate's standard error with the successive
difference replication formula,

$$
SE^2 = \frac{4}{160} \sum_{r=1}^{160} \left(\theta_r - \theta_0\right)^2,
$$

where $\theta_0$ uses the full-sample weight and $\theta_r$ the $r$-th
replicate weight. The 90 percent margin of error is $1.645 \times SE$. We
apply the formula to rates, numbers in poverty and element effects alike.

### Element effects (Table 5)

Table 5 reports, for each element of resources, the SPM rate minus the rate
without that element, with every other element held fixed. Removing an
addition lowers resources by its amount, and removing a subtraction raises
them by its amount. No published element has a negative amount in the file
(see the informational checks above), so additions never have positive
effects and subtractions never have negative ones. We map each element to
public-use fields as follows:

<!-- BEGIN GENERATED: elements -->
| Element | Kind | Public-use fields | In Table 5 |
| :-- | :-- | :-- | :-- |
| Social Security | Addition | `SS_VAL` summed over the unit's members | yes |
| Refundable tax credits | Addition | `SPM_EITC` + `SPM_ACTC` | yes |
| Earned Income Tax Credit (EITC) | Addition | `SPM_EITC` | yes |
| SNAP | Addition | `SPM_SNAPSUB` | yes |
| Child Tax Credit (refundable portion) | Addition | `SPM_ACTC` | yes |
| SSI | Addition | `SSI_VAL` summed over the unit's members | yes |
| Housing subsidies | Addition | `SPM_CAPHOUSESUB` | yes |
| School lunch | Addition | `SPM_SCHLUNCH` | yes |
| Child support received | Addition | `CSP_VAL` summed over the unit's members | yes |
| TANF/general assistance | Addition | `PAW_VAL` summed over the unit's members | yes |
| Unemployment insurance | Addition | `UC_VAL` summed over the unit's members | yes |
| Energy assistance | Addition | `SPM_ENGVAL` | yes |
| WIC | Addition | `SPM_WICVAL` | yes |
| Workers' compensation | Addition | `WC_VAL` summed over the unit's members | yes |
| Child support paid | Subtraction | `SPM_CHILDSUPPD` | yes |
| Federal income tax | Subtraction | `SPM_FEDTAXBC` | yes |
| Work expenses | Subtraction | `SPM_CAPWKCCXPNS` | yes |
| FICA | Subtraction | `SPM_FICA` | yes |
| Medical expenses | Subtraction | `SPM_MEDXPNS` | yes |
| State income tax | Subtraction | `SPM_STTAX` | no |
<!-- END GENERATED: elements -->

Resources also subtract state income tax, which Table 5 leaves out; we
report its effect without a published comparison. `SPM_STTAX` falls below
zero for some people, so removing it can raise poverty, and its effect can
take either sign.

### Characteristics (Table 4)

Table 4 gives the number and percentage of people in SPM poverty by
characteristic. The results table below lists the public-use definition of
each row.

## Results

### Table 5: the SPM rate and the effect of each element

All figures are in percentage points, with 90 percent margins of error. We
round our estimates to Census's two decimals; "Z" marks a published value
that rounds to zero.

<!-- BEGIN GENERATED: table5 -->
| Element | All people: ours | Census | Under 18: ours | Census | 18 to 64: ours | Census | 65 and older: ours | Census |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| SPM rate for all people | 13.11 ± 0.31 | 13.11 ± 0.31 | 13.39 ± 0.56 | 13.40 ± 0.56 | 12.28 ± 0.34 | 12.28 ± 0.34 | 15.38 ± 0.52 | 15.37 ± 0.53 |
| Social Security | -8.50 ± 0.18 | -8.52 ± 0.18 | -1.81 ± 0.21 | -1.82 ± 0.21 | -3.25 ± 0.16 | -3.26 ± 0.16 | -32.10 ± 0.72 | -32.13 ± 0.71 |
| Refundable tax credits | -1.81 ± 0.15 | -1.81 ± 0.15 | -4.51 ± 0.39 | -4.51 ± 0.38 | -1.40 ± 0.13 | -1.39 ± 0.13 | -0.13 ± 0.04 | -0.12 ± 0.04 |
| Earned Income Tax Credit (EITC) | -1.22 ± 0.13 | -1.19 ± 0.13 | -2.90 ± 0.31 | -2.85 ± 0.31 | -0.98 ± 0.11 | -0.95 ± 0.11 | -0.09 ± 0.04 | -0.08 ± 0.03 |
| SNAP | -0.92 ± 0.10 | -0.92 ± 0.10 | -1.63 ± 0.25 | -1.64 ± 0.26 | -0.68 ± 0.08 | -0.68 ± 0.08 | -0.90 ± 0.11 | -0.87 ± 0.11 |
| Child Tax Credit (refundable portion) | -0.71 ± 0.10 | -0.69 ± 0.09 | -1.89 ± 0.26 | -1.83 ± 0.25 | -0.51 ± 0.08 | -0.49 ± 0.07 | -0.03 ± 0.02 | -0.03 ± 0.02 |
| SSI | -0.65 ± 0.06 | -0.65 ± 0.06 | -0.40 ± 0.11 | -0.39 ± 0.11 | -0.63 ± 0.07 | -0.64 ± 0.07 | -0.98 ± 0.15 | -0.99 ± 0.15 |
| Housing subsidies | -0.61 ± 0.07 | -0.61 ± 0.06 | -0.80 ± 0.15 | -0.79 ± 0.15 | -0.43 ± 0.06 | -0.43 ± 0.06 | -0.97 ± 0.13 | -1.00 ± 0.14 |
| School lunch | -0.35 ± 0.06 | -0.35 ± 0.07 | -0.90 ± 0.17 | -0.91 ± 0.18 | -0.26 ± 0.05 | -0.26 ± 0.05 | -0.02 ± 0.02 | -0.02 ± 0.02 |
| Child support received | -0.15 ± 0.04 | -0.14 ± 0.04 | -0.40 ± 0.12 | -0.39 ± 0.12 | -0.11 ± 0.03 | -0.10 ± 0.03 | -0.01 ± 0.01 | -0.01 ± 0.01 |
| TANF/general assistance | -0.11 ± 0.03 | -0.11 ± 0.03 | -0.22 ± 0.08 | -0.21 ± 0.08 | -0.09 ± 0.03 | -0.09 ± 0.03 | -0.04 ± 0.02 | -0.04 ± 0.02 |
| Unemployment insurance | -0.10 ± 0.03 | -0.10 ± 0.03 | -0.13 ± 0.06 | -0.13 ± 0.06 | -0.12 ± 0.04 | -0.12 ± 0.04 | -0.03 ± 0.02 | -0.03 ± 0.02 |
| Energy assistance | -0.07 ± 0.02 | -0.07 ± 0.02 | -0.06 ± 0.03 | -0.06 ± 0.03 | -0.06 ± 0.02 | -0.06 ± 0.02 | -0.13 ± 0.05 | -0.11 ± 0.05 |
| WIC | -0.05 ± 0.02 | -0.05 ± 0.02 | -0.14 ± 0.05 | -0.13 ± 0.06 | -0.04 ± 0.02 | -0.04 ± 0.02 | 0.00 ± 0.00 | Z ± Z |
| Workers' compensation | -0.04 ± 0.02 | -0.04 ± 0.02 | -0.02 ± 0.02 | -0.02 ± 0.02 | -0.04 ± 0.02 | -0.04 ± 0.02 | -0.05 ± 0.03 | -0.05 ± 0.03 |
| Child support paid | 0.05 ± 0.02 | 0.04 ± 0.02 | 0.04 ± 0.03 | 0.03 ± 0.03 | 0.05 ± 0.02 | 0.05 ± 0.02 | 0.02 ± 0.02 | 0.02 ± 0.02 |
| Federal income tax | 0.42 ± 0.06 | 0.40 ± 0.06 | 0.36 ± 0.10 | 0.30 ± 0.09 | 0.51 ± 0.07 | 0.50 ± 0.08 | 0.21 ± 0.06 | 0.20 ± 0.06 |
| Work expenses | 1.18 ± 0.12 | 1.18 ± 0.12 | 1.76 ± 0.24 | 1.71 ± 0.23 | 1.26 ± 0.13 | 1.27 ± 0.13 | 0.30 ± 0.07 | 0.29 ± 0.07 |
| FICA | 1.32 ± 0.12 | 1.34 ± 0.12 | 1.80 ± 0.21 | 1.82 ± 0.21 | 1.46 ± 0.13 | 1.48 ± 0.14 | 0.38 ± 0.08 | 0.38 ± 0.08 |
| Medical expenses | 2.25 ± 0.13 | 2.28 ± 0.13 | 1.96 ± 0.21 | 1.99 ± 0.21 | 1.86 ± 0.14 | 1.88 ± 0.14 | 3.80 ± 0.26 | 3.83 ± 0.26 |
| State income tax | 0.11 ± 0.06 | not published | -0.04 ± 0.15 | not published | 0.17 ± 0.06 | not published | 0.07 ± 0.04 | not published |
<!-- END GENERATED: table5 -->

### Table 4: SPM poverty by characteristic

Percentages carry one decimal and numbers count thousands of people, as in
Census's table. "Within margin" says whether both our rate and our number
fall within Census's published margins of error.

<!-- BEGIN GENERATED: table4 -->
| Characteristic | Definition | Percent: ours | Census | Within margin | Number (thousands): ours | Census |
| :-- | :-- | --: | --: | :-- | --: | --: |
| All people | `Everyone` | 13.1 ± 0.3 | 13.1 ± 0.3 | yes | 44,390 ± 1,035 | 44,390 ± 1,042 |
| *Sex* |  |  |  |  |  |  |
| Male | `A_SEX = 1` | 12.4 ± 0.3 | 12.4 ± 0.3 | yes | 20,548 ± 557 | 20,580 ± 563 |
| Female | `A_SEX = 2` | 13.8 ± 0.4 | 13.8 ± 0.4 | yes | 23,843 ± 616 | 23,810 ± 614 |
| *Age* |  |  |  |  |  |  |
| Under 18 years | `A_AGE < 18` | 13.4 ± 0.6 | 13.4 ± 0.6 | yes | 9,653 ± 403 | 9,657 ± 399 |
| 18 to 64 years | `18 <= A_AGE < 65` | 12.3 ± 0.3 | 12.3 ± 0.3 | yes | 24,710 ± 676 | 24,710 ± 678 |
| 65 years and older | `A_AGE >= 65` | 15.4 ± 0.5 | 15.4 ± 0.5 | yes | 10,028 ± 342 | 10,020 ± 348 |
| *Type of Unit* |  |  |  |  |  |  |
| Married couple | `SPM_FAMTYPE = 1` | 7.8 ± 0.3 | 7.8 ± 0.3 | yes | 15,722 ± 661 | 15,710 ± 649 |
| Cohabiting partners | `SPM_FAMTYPE = 2` | 12.9 ± 1.1 | 13.1 ± 1.2 | yes | 3,535 ± 337 | 3,592 ± 344 |
| Female reference person | `SPM_FAMTYPE = 3` | 25.0 ± 1.2 | 25.0 ± 1.2 | yes | 10,710 ± 595 | 10,690 ± 592 |
| Male reference person | `SPM_FAMTYPE = 4` | 17.9 ± 1.8 | 17.9 ± 1.8 | yes | 3,021 ± 325 | 3,024 ± 326 |
| Unrelated individuals | `SPM_FAMTYPE = 5` | 23.3 ± 0.8 | 23.2 ± 0.8 | yes | 11,403 ± 435 | 11,370 ± 439 |
| *Race and Hispanic Origin* |  |  |  |  |  |  |
| White | `PRDTRACE = 1` | 11.8 ± 0.4 | 11.8 ± 0.4 | yes | 28,988 ± 857 | 28,910 ± 855 |
| White, not Hispanic | `PRDTRACE = 1 and PEHSPNON = 2` | 9.2 ± 0.4 | 9.2 ± 0.4 | yes | 17,499 ± 667 | 17,430 ± 673 |
| Black | `PRDTRACE = 2` | 20.1 ± 1.0 | 20.3 ± 1.0 | yes | 9,155 ± 473 | 9,219 ± 476 |
| Asian | `PRDTRACE = 4` | 12.7 ± 1.2 | 12.8 ± 1.2 | yes | 3,209 ± 304 | 3,254 ± 306 |
| American Indian and Alaska Native | `PRDTRACE = 3` | 18.5 ± 2.6 | 18.1 ± 2.6 | yes | 936 ± 152 | 918 ± 149 |
| Two or More Races | `PRDTRACE >= 6` | 12.6 ± 1.6 | 12.5 ± 1.5 | yes | 1,929 ± 248 | 1,913 ± 241 |
| Hispanic (any race) | `PEHSPNON = 1` | 20.0 ± 1.0 | 20.0 ± 0.9 | yes | 14,035 ± 673 | 14,000 ± 664 |
| *Nativity* |  |  |  |  |  |  |
| Native-born | `PRCITSHP in 1-3` | 12.0 ± 0.3 | 11.9 ± 0.3 | yes | 34,270 ± 865 | 34,170 ± 868 |
| Foreign-born | `PRCITSHP in 4-5` | 19.3 ± 0.8 | 19.5 ± 0.8 | yes | 10,120 ± 468 | 10,220 ± 470 |
| Naturalized citizen | `PRCITSHP = 4` | 15.1 ± 0.9 | 15.2 ± 0.9 | yes | 4,123 ± 250 | 4,131 ± 248 |
| Not a citizen | `PRCITSHP = 5` | 23.9 ± 1.3 | 24.3 ± 1.3 | yes | 5,998 ± 359 | 6,093 ± 363 |
| *Educational Attainment* |  |  |  |  |  |  |
| Total, 25 years old and older | `A_AGE >= 25` | 12.4 ± 0.3 | 12.4 ± 0.3 | yes | 29,241 ± 674 | 29,270 ± 678 |
| No high school diploma | `A_AGE >= 25 and A_HGA <= 38` | 32.5 ± 1.3 | 32.4 ± 1.3 | yes | 5,888 ± 273 | 5,870 ± 274 |
| High school, no college | `A_AGE >= 25 and A_HGA = 39` | 16.9 ± 0.5 | 16.9 ± 0.5 | yes | 10,899 ± 374 | 10,890 ± 376 |
| Some college | `A_AGE >= 25 and A_HGA in 40-42` | 11.0 ± 0.4 | 11.0 ± 0.5 | yes | 6,417 ± 269 | 6,448 ± 274 |
| Bachelor's degree or higher | `A_AGE >= 25 and A_HGA >= 43` | 6.4 ± 0.3 | 6.4 ± 0.3 | yes | 6,036 ± 280 | 6,058 ± 285 |
| *Tenure* |  |  |  |  |  |  |
| Owner/mortgage | `SPM_TENMORTSTATUS = 1` | 6.0 ± 0.4 | 6.0 ± 0.4 | yes | 8,476 ± 522 | 8,476 ± 523 |
| Owner/no mortgage/rent free | `SPM_TENMORTSTATUS = 2` | 11.9 ± 0.5 | 11.9 ± 0.5 | yes | 11,175 ± 500 | 11,150 ± 503 |
| Renter | `SPM_TENMORTSTATUS = 3` | 24.0 ± 0.8 | 24.0 ± 0.8 | yes | 24,739 ± 944 | 24,760 ± 934 |
| *Residence* |  |  |  |  |  |  |
| Inside metropolitan statistical areas | `GTMETSTA = 1` | 13.3 ± 0.3 | 13.2 ± 0.3 | not testable | 38,548 ± 977 | 38,820 ± 1,052 |
| Inside principal cities | `GTMETSTA = 1 and GTCBSAST = 1` | 17.1 ± 0.7 | 16.8 ± 0.7 | not testable | 15,796 ± 721 | 18,450 ± 886 |
| Outside principal cities | `GTMETSTA = 1 and GTCBSAST = 2` | 11.3 ± 0.4 | 11.0 ± 0.4 | not testable | 17,464 ± 680 | 20,370 ± 723 |
| Outside metropolitan statistical areas | `GTMETSTA = 2` | 12.1 ± 0.8 | 12.8 ± 0.9 | not testable | 5,567 ± 440 | 5,570 ± 525 |
| *Region* |  |  |  |  |  |  |
| Northeast | `GEREG = 1` | 12.7 ± 0.8 | 12.9 ± 0.8 | yes | 7,277 ± 462 | 7,382 ± 467 |
| Midwest | `GEREG = 2` | 9.8 ± 0.7 | 9.9 ± 0.7 | yes | 6,810 ± 468 | 6,839 ± 474 |
| South | `GEREG = 3` | 14.2 ± 0.5 | 14.1 ± 0.5 | yes | 18,760 ± 624 | 18,620 ± 631 |
| West | `GEREG = 4` | 14.5 ± 0.7 | 14.5 ± 0.7 | yes | 11,544 ± 526 | 11,540 ± 519 |
| *Health Insurance Coverage* |  |  |  |  |  |  |
| With private insurance | `PRIV = 1` | 6.1 ± 0.2 | 6.1 ± 0.2 | yes | 13,440 ± 549 | 13,450 ± 541 |
| With public, no private insurance | `PUB = 1 and PRIV != 1` | 26.6 ± 0.7 | 26.6 ± 0.8 | yes | 23,761 ± 758 | 23,750 ± 768 |
| Not insured | `COV in {0, 2}` | 26.3 ± 1.1 | 26.3 ± 1.1 | yes | 7,189 ± 392 | 7,191 ± 390 |
| *Work Experience* |  |  |  |  |  |  |
| Total, 18 to 64 years old | `18 <= A_AGE < 65` | 12.3 ± 0.3 | 12.3 ± 0.3 | yes | 24,710 ± 676 | 24,710 ± 678 |
| All workers | `18 <= A_AGE < 65 and WEXP in 1-12` | 7.1 ± 0.3 | 7.1 ± 0.3 | yes | 11,257 ± 438 | 11,290 ± 442 |
| Worked full-time, year-round | `18 <= A_AGE < 65 and WEXP = 1` | 4.1 ± 0.2 | 4.1 ± 0.2 | yes | 4,816 ± 262 | 4,822 ± 266 |
| Less than full-time, year-round | `18 <= A_AGE < 65 and WEXP in 2-12` | 15.5 ± 0.7 | 15.5 ± 0.7 | yes | 6,441 ± 323 | 6,470 ± 332 |
| Did not work | `18 <= A_AGE < 65 and WEXP = 13` | 31.3 ± 0.8 | 31.3 ± 0.8 | yes | 13,453 ± 432 | 13,420 ± 431 |
| *Disability Status* |  |  |  |  |  |  |
| Total, 18 to 64 years old | `18 <= A_AGE < 65` | 12.3 ± 0.3 | 12.3 ± 0.3 | yes | 24,710 ± 676 | 24,710 ± 678 |
| With a disability | `18 <= A_AGE < 65 and PRDISFLG = 1` | 25.0 ± 1.2 | 25.0 ± 1.2 | yes | 4,146 ± 227 | 4,147 ± 228 |
| With no disability | `18 <= A_AGE < 65 and PRDISFLG = 2` | 11.2 ± 0.3 | 11.2 ± 0.3 | yes | 20,506 ± 622 | 20,510 ± 623 |
<!-- END GENERATED: table4 -->

## Where the reproduction falls short

We use Census's own records, weights and SPM fields, so sampling does not
cause the remaining gaps. Census's margins of error give their scale, not
their cause.

<!-- BEGIN GENERATED: largest_gaps -->
Table 5 effects that differ from Census's by 0.03 points or more:

| Element | Group | Ours | Census | Gap |
| :-- | :-- | --: | --: | --: |
| Child Tax Credit (refundable portion) | Under 18 years | -1.89 | -1.83 | 0.06 |
| Federal income tax | Under 18 years | 0.36 | 0.30 | 0.06 |
| Earned Income Tax Credit (EITC) | Under 18 years | -2.90 | -2.85 | 0.05 |
| Work expenses | Under 18 years | 1.76 | 1.71 | 0.05 |
| Earned Income Tax Credit (EITC) | All people | -1.22 | -1.19 | 0.03 |
| Earned Income Tax Credit (EITC) | 18 to 64 years | -0.98 | -0.95 | 0.03 |
| Housing subsidies | 65 years and older | -0.97 | -1.00 | 0.03 |
| Medical expenses | All people | 2.25 | 2.28 | 0.03 |
| Medical expenses | Under 18 years | 1.96 | 1.99 | 0.03 |
| Medical expenses | 65 years and older | 3.80 | 3.83 | 0.03 |
| SNAP | 65 years and older | -0.90 | -0.87 | 0.03 |
| Social Security | 65 years and older | -32.10 | -32.13 | 0.03 |

Identifiable Table 4 rows whose percentage differs from Census's by 0.2 points or more:

| Characteristic | Ours | Census | Gap | Census margin |
| :-- | --: | --: | --: | --: |
| American Indian and Alaska Native | 18.5 | 18.1 | 0.4 | 2.6 |
| Not a citizen | 23.9 | 24.3 | 0.4 | 1.3 |
| Black | 20.1 | 20.3 | 0.2 | 1.0 |
| Cohabiting partners | 12.9 | 13.1 | 0.2 | 1.2 |
| Foreign-born | 19.3 | 19.5 | 0.2 | 0.8 |
| Northeast | 12.7 | 12.9 | 0.2 | 0.8 |
<!-- END GENERATED: largest_gaps -->

**Refundable credits.** Our combined effect of the Earned Income Tax Credit
and the refundable Child Tax Credit matches Census's within 0.01 point in
every age group. Yet for all people, and for both age groups under 65, our
effect of each credit alone exceeds Census's in magnitude. We have not found
a public-use definition that reproduces each credit alone. The file's
tax-unit credits (`EIT_CRED`, `ACTC_CRD`) sum exactly to its SPM unit fields,
so reading either gives the same effects.

**Federal income tax.** Census's federal income tax row removes tax before
refundable credits (`SPM_FEDTAXBC`) and shows the credits as their own rows.
Removing tax after credits (`SPM_FEDTAX`) instead lands far from Census's
row:

<!-- BEGIN GENERATED: alternatives -->
| Published row | Our definition | Alternative | Census |
| :-- | --: | --: | --: |
| Federal income tax (Table 5, all people) | 0.42 | Federal income tax after refundable credits: -1.39 | 0.40 ± 0.06 |
| Cohabiting partners (Table 4, percent) | 12.9 | Cohabiting partners, by the unit head's code: 12.9 | 13.1 ± 1.2 |
| Not insured (Table 4, percent) | 26.3 | Not insured, without infants born after the calendar year: 26.6 | 26.3 ± 1.1 |
<!-- END GENERATED: alternatives -->

**Health insurance.** The data dictionary codes infants born after the
calendar year as `COV = 0`. Counting them as not insured reproduces Census's
row; leaving them out moves our rate away from it, as the last row of the
table above shows.

**Unit type.** The data dictionary describes `SPM_FAMTYPE` as the "SPM
unit's family type", yet members of some units carry different codes (see
the informational checks above). We use each person's own code. Reading the
unit head's code instead leaves the cohabiting-partner rate unchanged at the
published decimal, so that choice does not explain the gap in that row.

**Residence.** Census's residence rows need geography that the public-use
file withholds for some households:

<!-- BEGIN GENERATED: geography -->
The public-use file leaves metropolitan status unidentified (GTMETSTA = 3) for 1,526 sample people, 2,710 thousand weighted, and principal-city status unidentified (GTCBSAST = 4) for 22,574 sample people, 46,170 thousand weighted. Census's table places everyone: its inside- and outside-metropolitan numbers in poverty, 38,820 and 5,570 thousand, sum to 44,390 thousand, against 44,390 thousand for all people.
<!-- END GENERATED: geography -->

We report the four residence rows but leave them out of the tolerance
tests.

## Tolerances

The tests hold the committed results to the tolerances below. We set each
one at the largest gap we found, rounded up to the published precision (to
the next whole percent for the relative margin), so that any code change
that widens a gap fails the tests. The tolerances describe this
reproduction; Census sets no such standard. The tests also require our SPM
rate for all people, and its margin of error, to equal Census's at the
published two decimals.

<!-- BEGIN GENERATED: tolerances -->
| Comparison | Tolerance | Largest gap |
| :-- | --: | --: |
| Table 5 SPM rate, each age group | 0.01 points | 0.01 |
| Table 5 SPM rate margin of error | 0.01 points | 0.01 |
| Table 5 element effect | 0.06 points | 0.06 |
| Table 5 element effect margin of error | 0.01 points | 0.01 |
| Table 4 percent, identifiable rows | within the published margin | 45 of 45 rows |
| Table 4 number, identifiable rows | within the published margin | 45 of 45 rows |
| Table 4 percent margin of error | 0.1 points | 0.1 |
| Table 4 number margin of error | 3 percent | 2.8 percent |
<!-- END GENERATED: tolerances -->

## Rebuilding the numbers

The script reads the zip from the package's CPS ASEC cache
(`$SPM_CALCULATOR_CPS_CACHE`, or `~/.cache/spm-calculator/cps-asec`), and
`--download` fetches it from Census when it is missing:

```bash
uv run --no-sync python scripts/reproduce_census_spm.py --download
```

The script checks every input's SHA-256, rewrites the results file and this
note's generated blocks, and exits with an error if any tolerance fails. To
check the committed results and note against a fresh rebuild without
writing anything:

```bash
uv run --no-sync python scripts/reproduce_census_spm.py --check
```

The test suite runs the same comparison when the zip sits in the cache and
`SPM_CALCULATOR_CENSUS_SPM_REBUILD=1` is set.

## Next steps

The [series plan](spm-evidence-series.md) describes how the later steps
replace Census's taxes, tax units, benefits, imputations and weights with
PolicyEngine's, one at a time, starting from the numbers above.
