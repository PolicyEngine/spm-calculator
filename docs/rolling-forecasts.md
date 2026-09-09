# Rolling expenditure and rent forecasts

The calculator projects missing observations and advances the expenditure and
rent windows used to estimate SPM thresholds. Price growth and real spending
growth are separate assumptions. An inflation-only projection holds the real
spending of new observations constant; it does not imply that actual real
spending will remain constant.

This is a public-data research projection. The [published release](spm-releases.md)
and archived forecast commitments retain their original bytes. The new artifact
has its own information date, source receipts and content digest. Its Python
consumer works without PolicyEngine, Microcosm, Axiom or a network connection.

## Reference years and moving windows

The revised [BLS methodology](https://www.bls.gov/pir/spm/spm_thresholds_2025.htm)
uses five years of CE data lagged by one year. A threshold for reference year
T uses collection quarters (T−5)Q2 through TQ1. The current observed files end
in 2025Q1. The [Census SPM geography method](https://www2.census.gov/programs-surveys/supplemental-poverty-measure/datasets/spm/spm_techdoc.pdf)
uses the preceding five calendar years of ACS rents.

| SPM reference year | CE collection window | Projected CE quarters | ACS calendar window | Projected ACS cohorts |
| --- | --- | ---: | --- | ---: |
| 2024 | 2019Q2–2024Q1 | 0 | 2019–2023 | 0 |
| 2025 | 2020Q2–2025Q1 | 0 | 2020–2024 | 0 |
| 2026 | 2021Q2–2026Q1 | 4 | 2021–2025 | 1 |
| 2027 | 2022Q2–2027Q1 | 8 | 2022–2026 | 2 |
| 2028 | 2023Q2–2028Q1 | 12 | 2023–2027 | 3 |
| 2029 | 2024Q2–2029Q1 | 16 | 2024–2028 | 4 |
| 2030 | 2025Q2–2030Q1 | 20 | 2025–2029 | 5 |

National thresholds for 2024 and 2025 use the published BLS values directly.
Census's published 2024 indices and housing shares anchor geographic levels.
The 2025 local amount uses a published national base and modeled geographic
inputs; it is not a wholly published threshold. Census has [scheduled its
2025 poverty release for September 15, 2026](https://www.census.gov/newsroom/press-releases/2026/2025-iphi-webinar-advisory.html).
The source check records the actual acquisition date, September 9 UTC.

## Prices and real spending

For a missing CE quarter, the donor is the latest observed quarter in the
same season. For example, projected 2026Q1 uses observed 2025Q1, while
projected 2025Q2 uses observed 2024Q2. Demographics, tenure, weights and
missing-value patterns stay with that donor. Monetary expenditures scale by:

`projected expenditure = donor expenditure × price factor × real spending factor`.

The price factor uses the CE composite index with weights from the origin's
five-year sample. Historical annual CPI observations are pinned. The package
assumes inflation of 2.3% in 2026, 2.2% in 2027 and 2.0% in 2028–2030. These
are declared scenarios, without an external BLS or CBO forecast vintage.
The committed BLS API receipt verifies all-items CPI-U annual averages of
313.689 for 2024 and 321.943 for 2025. The latter covers eleven months:
October 2025 data were not collected.

Two spending scenarios use the same historical records and price path:

- **No real spending growth (`zero_real`)** gives new observations a real
  spending factor of one.
- **CE real-spending trend (`ce_trend`)** fits the log of near-median FCSU
  expenditures in five nonoverlapping annual blocks ending in Q1. All blocks
  use the same reference-family normalization and origin-year prices. The
  forecast applies half the fitted annual log slope: a declared 0.5 shrinkage
  toward zero. For a donor advanced by k years, the real factor is
  `exp(0.5 × fitted log slope × k)`.

Each annual block selects its own 47–53 percentile expenditure band. The
trend may be negative. Ten-block and pandemic-excluded fits show sensitivity
to the estimation period; the latter excludes blocks ending in 2021Q1 and
2022Q1. Ordinary least-squares slope standard errors describe the fit, not
survey-design uncertainty or a forecast interval. The default `ce_trend`
specification was selected independently of the retrospective test results.
It is not labeled the best-performing model.

The current-origin fits in the [pinned CE component](../spm_calculator/data/current/ce_rolling_forecast.json)
give the following annual rates after the declared 0.5 shrinkage:

| Fit | Annual blocks | Annual real spending growth |
| --- | ---: | ---: |
| Five-year trend | 5 | 0.9143% |
| Ten-year trend | 10 | 0.8167% |
| Pandemic-excluded trend | 3 | −0.1354% |

The difference between these fits is sensitivity to the estimation period,
not a confidence interval.

Aggregate real consumption growth is not interchangeable with real FCSU
spending among families near the SPM estimation range. The common real-growth
scenario also holds future sample composition and relative category spending
fixed. It does not model changing household composition or behavioral
responses. Existing [CE replication approximations](current-ce-replication.md)
remain, including annual price treatment and omitted internet and in-kind
imputations.

## Thresholds and housing shares

Every projected year reruns the CE estimator on its own twenty-quarter
window. Let C(T,h) be its raw national threshold for year T and tenure h.
Future national thresholds use:

`threshold(T,h) = published threshold(2025,h) × C(T,h) / C(2025,h)`.

The estimator's housing fraction is `0.82 × tenure SU mean / C(T,h)`.
The projected housing share equals the published Census 2024 share times
the ratio of that estimated fraction in T to its value in 2024. Anchoring
recovers the published base exactly. Shares outside (0,1) cause an error.

The sample and composite-price weights are recomputed inside each target
window. Donor scaling uses the frozen origin weights to bridge price years;
the estimator then applies only the remaining target-year price adjustment.
This is an explicit approximation, with no second application of the same
inflation interval.

A positive real-growth assumption need not raise every tenure's threshold
at every horizon. For 2026, the national renter threshold is $43,563.48 under
`ce_trend`, compared with $43,621.68 under `zero_real`. The reselected band's
mean FCSU spending rises by $76.00, while its overall SU mean rises by $127.16
and renter SU mean falls by $33.04. BLS's tenure formula subtracts the overall
SU mean and adds the tenure mean, so the housing adjustment offsets the
increase in common spending. By 2030 the renter thresholds are $49,099.08
and $48,061.18 respectively. These are generated research results from the
pinned CE component, not published BLS forecasts.

## Geographic rent indices

ACS inputs are cash-rented, occupied two-bedroom housing units with complete
kitchen and plumbing, positive gross rent and positive survey weight.
`GRNTP × ADJHSG / 1,000,000` applies the source product's dollar adjustment
once. The calculation pools weighted individual records; it does not average
annual medians. Census explains [why multiyear estimates describe a pooled
period](https://www.census.gov/newsroom/blogs/random-samplings/2022/03/period-estimates-american-community-survey.html).

Public PUMS identifies PUMAs rather than exact Census SPM areas. A pinned
fractional PUMA-to-county-to-area mapping uses 2020 geography and Census's
2013 metropolitan definitions. This is a geographic approximation. The
published 341-area menu does not partition every county: unmatched menu
fractions remain in the full-US national median and are reported separately.
Every requested area must have positive coverage.

The 2019–2023 and 2020–2024 PUMS products have different weights and dollar
vintages. Let R be the modeled ratio of local to national pooled median rent.
The forecast bridges the common 2020–2023 period:

`index(T) = official index(2024) × R(old overlap)/R(old full) × R(new T)/R(new overlap)`.

Each ratio uses records from one product. The overlap comparison removes the
measured common-window vintage shift; it does not eliminate every revision
effect. The four-year overlap uses the five-year product's supplied weights
and is not an official four-year estimate. Weighted microdata medians also
approximate Census's grouped-data interpolation.

Missing ACS years copy the observed 2024 cohort. Baseline nominal gross rents
grow at the all-items CPI path and are deflated by that same path. New cohorts
therefore have zero real rent growth. Historical cohorts still roll out, so
local and national pooled medians can change differently. A separate
sensitivity adds two percentage points to each missing year's nominal rent
growth while leaving the deflator unchanged. The CE spending scenario does
not change this ACS assumption.

For housing share s and rent index I, the location factor is `1 + s × (I−1)`.
Both s and I can change over time. Equal future growth alone does not imply
a constant factor. A proportional local-to-national distribution throughout
the entire history would instead preserve the rent-index ratio.

## Support and topcoding

Repeated projected copies do not create new original observations. Diagnostics
combine their allocation-adjusted weights by original record before computing
the Kish count, `(sum weights)² / sum(weights²)`. An expected whole-record
count sums each original's geographic allocation fraction once. An area is
flagged when the minimum of unique records, expected count and Kish count is
below 30. This is a declared research heuristic, not a Census publication
standard or a survey-design effective sample size.

The artifact reports cohort-specific cash-rent and utility topcoding flags,
affected weight shares and a conservative median warning. A median below the
cash-rent topcode does not prove that utility topcoding is irrelevant. Thin
areas retain their values and warnings; the consumer never substitutes a
different geography.

## Retrospective evaluation

CE forecasts use origins 2019–2024 and targets through 2025, giving 6, 5, 4,
3, 2 and 1 folds at horizons one through six. Each fold uses its own published
revised-method origin threshold and only CE records through that origin's Q1.
Both candidates and the inflation-only comparator use realized annual prices
through the target. These are current-vintage, price-conditional retrospective
tests, not a reconstruction of real-time forecast accuracy.

The primary error is mean absolute percentage error (MAPE), equally weighting
the 63 fold-tenure results. Short horizons have more folds. A second metric
equally weights the per-horizon MAPEs for displayed horizons one through five.
The app warns when a scenario fails to beat the CPI-only baseline overall,
on that horizon-balanced measure, or at the selected forecast horizon.

The ACS holdout uses the corrected 2018–2022 product, anchors to the official
2023 index, drops 2018 and adds a projected copy of the 2022 cohort as 2023.
It compares predicted 2024 indices with official 2024 values and unchanged
2023 indices across all 341 areas. Its primary metric equally weights area
absolute percentage errors. This tests the donor mechanism, not the later
cross-vintage bridge. The app flags failure to improve on unchanged indices.

Results from the pinned CE and [ACS components](../spm_calculator/data/current/acs_rolling_forecast.json):

| CE method | Overall MAPE | Horizon-balanced MAPE, years 1–5 | One-year MAPE |
| --- | ---: | ---: | ---: |
| CE real-spending trend | 2.8428% | 3.3276% | 0.7152% |
| No real spending growth | 3.1487% | 3.6955% | 0.6512% |
| All-items CPI extrapolation | 5.3117% | 5.9268% | 2.2868% |

Both rolling methods outperform CPI extrapolation at every evaluated horizon.
Zero real growth performs slightly better at one year; the trend performs
better on the overall and horizon-balanced comparisons. Only two folds
inform the five-year result and one informs the supplemental six-year result.
The ACS donor method's MAPE is 1.2537%, compared with 1.7284% for unchanged
indices. Its median absolute percentage error is 0.8745%, compared with
1.5048%. These comparisons have the source-vintage and price-conditioning
limits described above.

Missing folds, areas or invalid results block generation. Numerical
underperformance is reported rather than treated as a data failure. The
artifact also freezes a hashed 2025 geographic prediction for comparison with
the later official workbook; that forward test is pending official data.
Neither these tests nor the fitted trend provide forecast uncertainty bounds.

## Standalone calculation

This preview API is developed in [calculator PR 36](https://github.com/PolicyEngine/spm-calculator/pull/36)
and is not yet published on PyPI:

```python
from spm_calculator import load_forecast, SPMUnit

projection = load_forecast()  # Pass expected_sha256 to pin a retained artifact.
result = projection.calculate_unit(
    SPMUnit(
        unit_id="household-1",
        num_adults=2,
        num_children=2,
        tenure="renter",
        year=2026,
        geography_kind="metro",
        geography_id="41860",
    ),
    scenario="ce_trend",
)
print(result["threshold"])
```

The result records the scenario, artifact identity, component statuses,
year-specific inputs and selected-area diagnostics. Unknown areas, years and
scenarios raise errors. An `as_of` date before the artifact's information
date also raises an error. PolicyEngine, Axiom and Microcosm production
integrations have not adopted this new research forecast in this change.

## Rebuild and verify

Raw CE ZIPs and ACS PUMS products stay in configurable external caches. The
component manifests pin their URLs and hashes; compact crosswalks and source
receipts ship with the package. With matching raw source bytes cached:

```sh
uv run --no-sync python scripts/build_ce_forecast.py --output spm_calculator/data/current/ce_rolling_forecast.json
uv run --no-sync python scripts/build_acs_forecast.py --output spm_calculator/data/current/acs_rolling_forecast.json
uv run --no-sync python scripts/build_rolling_forecast.py
uv run --no-sync python scripts/export_web_release.py
```

Both scientific builders support `--cache-dir` and an offline `--check` that
repeats the calculations from cached raw inputs. The assembly check below
uses committed component results, verifies their scientific code and package
input hashes, checks the official CPI receipt and required evaluation
coverage, and reproduces the portable artifact without raw microdata:

```sh
uv run --no-sync python scripts/build_rolling_forecast.py --check
uv run --no-sync python scripts/export_web_release.py --check
```

Changing scientific code or pinned inputs requires rebuilding the affected
component before assembly. Hashes check integrity; they are not signatures
or independent evidence of source authenticity.
