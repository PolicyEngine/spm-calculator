# The 2026 BLS threshold correction

On July 17, 2026, the Census Bureau [announced](https://www.census.gov/newsroom/press-releases/2026/statement-on-supplemental-poverty-measure.html) that BLS had found errors in the Supplemental Poverty Measure thresholds and would re-release SPM estimates for 2019–2024. BLS [reissued corrected thresholds](https://www.bls.gov/pir/spm/spm_thresholds_2024_correction.htm) the same day, attributing the errors to "corrections to the computer code used to generate the thresholds" introduced with the September 2021 methodology change, and re-derived the median anchor from 83% to 82% of the 47th–53rd percentile FCSUti average to minimize the break in series.

This page documents what changed, what this package shipped before version 0.4, and what an independent replication of the BLS methodology can and cannot detect.

## How large the BLS correction is

Two-adult, two-child national thresholds, as published in the Census P60 reports versus the corrected workbook:

| Year | Tenure | Published | Corrected | Change |
|---|---|---|---|---|
| 2019 | Owner w/ mortgage | 29,080 | 29,076.17 | −0.0% |
| 2019 | Owner w/o mortgage | 24,413 | 24,514.95 | +0.4% |
| 2019 | Renter | 29,194 | 28,913.05 | −1.0% |
| 2020 | Owner w/ mortgage | 29,959 | 29,814.55 | −0.5% |
| 2020 | Owner w/o mortgage | 25,222 | 25,249.14 | +0.1% |
| 2020 | Renter | 30,150 | 29,978.90 | −0.6% |
| 2021 | Owner w/ mortgage | 31,107 | 30,983.24 | −0.4% |
| 2021 | Owner w/o mortgage | 26,279 | 26,055.40 | −0.9% |
| 2021 | Renter | 31,453 | 31,216.69 | −0.8% |
| 2022 | Owner w/ mortgage | 34,235 | 33,978.49 | −0.7% |
| 2022 | Owner w/o mortgage | 28,909 | 28,454.92 | −1.6% |
| 2022 | Renter | 34,518 | 34,140.06 | −1.1% |
| 2023 | Owner w/ mortgage | 36,915 | 36,966.24 | +0.1% |
| 2023 | Owner w/o mortgage | 30,870 | 30,587.73 | −0.9% |
| 2023 | Renter | 37,482 | 37,230.75 | −0.7% |
| 2024 | Owner w/ mortgage | 39,068 | 39,231.00 | +0.4% |
| 2024 | Owner w/o mortgage | 32,586 | 32,878.59 | +0.9% |
| 2024 | Renter | 39,430 | 39,219.89 | −0.5% |

Every change is within ±1.6%. Census will quantify the effect on SPM poverty rates in a working paper before the September 2026 report.

This is BLS's second code-correction episode in this series: the P60-280 threshold table footnote records that the 2022 thresholds already reflected "corrections in the computer code used to model" in-kind benefits.

## What this package shipped before 0.4

Versions through 0.3.1 hand-entered the threshold dict. Comparing it against what Census actually published:

| Year | Package ≤0.3.1 (renter) | Published (renter) | Error |
|---|---|---|---|
| 2019 | 27,515 | 29,194 | −5.8% |
| 2020 | 28,881 | 30,150 | −4.2% |
| 2021 | 31,453 | 31,453 | 0.0% |
| 2022 | 33,402 | 34,518 | −3.2% |
| 2023 | 36,606 | 37,482 | −2.3% |
| 2024 | 39,430 | 39,430 | 0.0% |

Owner-tenure errors reach −7.4% (2019). The 2019–2020 rows appear to be misattributed vintages (old-methodology 2019, and a value set matching no publication for 2020); 2022–2023 match no BLS or Census publication we could locate. Only 2021 (renter) and 2024 were correct.

Two conclusions follow. First, the package's own data errors were several times larger than the BLS error that prompted this work. Second, hand-entered reference data is the failure mode — in both organizations.

## What 0.4 changes

- **Provenance-tracked series.** `scripts/build_threshold_series.py` is the only writer of the packaged data. It parses the official BLS workbook (bundled, SHA-256 recorded) and emits full-precision thresholds, standard errors, and tenure shares for 2005–2024.
- **Three bundled series.** `bls-corrected-2026-07-17` (default), `census-published-pre-correction` (what every published 2019–2024 SPM statistic used, cross-verified against two consecutive P60 reports per year), and `package-legacy-0.3` (verbatim, for reproducing results from earlier releases).
- **Drift watch.** A weekly CI job re-downloads the BLS workbook and diffs it against the packaged series, opening an issue on divergence. Either failure mode above — ours or theirs — now surfaces within a week.
- **Replication fixes.** Benchmarking the CE-based replication against both reference series surfaced four bugs in our own methodology code, detailed below.

## Could an independent replication have caught the BLS bug?

This package includes a from-scratch implementation of the BLS threshold methodology over raw Consumer Expenditure PUMD. We benchmarked it for target years 2019–2024 against both the published and corrected series (`scripts/benchmark_bls_replication.py`), matching each comparison's anchor (83% versus published, 82% versus corrected) so anchor choice cannot manufacture a fit.

Building the benchmark surfaced four errors in our replication code, none previously detected because the validation test allowed 5% tolerance and was skipped by default:

1. **Annualization off by 2×.** FMLI's `*PQ`/`*CQ` pair is one three-month recall window split across calendar quarters; the code treated it as six months of spending and multiplied by 2 instead of 4.
2. **Telephone double-counted.** The FMLI `UTIL` summary already contains `TELEPH`; the code added telephone again.
3. **Phantom columns.** The mortgage-principal (`MRTPRINPQ`) and internet (`INFOTECHPQ`) columns the code referenced do not exist in FMLI; both silently contributed zero. Principal now uses the real outlay columns (`EMRTPNO*`, `MRTPRNO*`); internet has no FMLI summary variable and is a documented gap.
4. **Wrong formula shape.** The code took per-tenure percentiles of the FCSUti distribution. BLS computes `0.82 × (1.2 × FCSUti_E − SU_E + SU_Eh)` over a pooled 47th–53rd percentile estimation sample, swapping the tenure-specific shelter-utilities average — including the 1.2 multiplier for other basic goods and services.

After the fixes, the faithful variant (BLS quarter window, principal-inclusive shelter, ×4 annualization) replicates official thresholds within **1–4.5% mean absolute deviation per year** with no imputed in-kind benefits. Signed deviations for the matched-anchor comparisons:

| Year | vs published (83%) | vs corrected (82%) |
|---|---|---|
| 2019 | +4.0 / +6.6 / +3.1% | +2.7 / +4.9 / +2.9% |
| 2020 | +2.9 / +5.0 / +2.3% | +2.2 / +3.6 / +1.6% |
| 2021 | +1.2 / +3.1 / +0.7% | +0.4 / +2.8 / +0.2% |
| 2022 | −1.7 / +0.3 / −1.9% | −2.1 / +0.7 / −2.0% |
| 2023 | −3.4 / −2.5 / −3.6% | −4.7 / −2.8 / −4.1% |
| 2024 | −2.4 / +0.1 / −3.2% | −4.0 / −2.0 / −3.9% |

(Owner w/ mortgage / owner w/o mortgage / renter. The downward drift across years is consistent with the growing in-kind benefit imputations — broadband, LIHEAP, NSLP, WIC, rental assistance — that BLS adds to consumer-unit FCSUti and this replication does not.)

The answer to the headline question is no. The BLS correction moved thresholds by at most 1.6%; the replication's own noise floor is 2–4%, and neither reference series fits systematically better in the affected years. A survey-level replication validates the structure of the series — it caught our 2–8% data errors' worth of divergence instantly once pointed at real references — but it cannot resolve a sub-2% code error inside BLS's pipeline.

What does catch that class of error on day one is mechanical: diffing published artifacts. The drift watch now does this weekly. It would have flagged this package's hand-entry errors on its first run, and BLS's July 17 reissue on the first Monday after.

One further check the replication does support: at matched anchors, the 83% variant fits the published series about as well as the 82% variant fits the corrected one — independent confirmation that BLS's re-anchoring preserved series continuity, as intended.

## 2025 published

BLS finalized the 2025 research SPM thresholds on August 24, 2026. The current workbook provides full-precision thresholds, standard errors, and tenure shares; its thresholds round to the values on the BLS publication page:

| Tenure | Full-precision workbook | BLS page | Growth from corrected 2024 |
|---|---:|---:|---:|
| Owner w/ mortgage | $41,322.71 | $41,323 | 5.332% |
| Owner w/o mortgage | $34,326.00 | $34,326 | 4.402% |
| Renter | $41,700.56 | $41,701 | 6.325% |

The package's committed nowcast is now an evaluation artifact rather than a current estimate. Against the full-precision actuals, it missed by −0.69%, −0.55%, and −2.27% respectively, for a **1.17% mean absolute error** across tenures. For comparison, aging the corrected 2024 base by CPI-U missed by 2.58%, the CE replication ratio alone missed by 0.75%, and the original pre-composite-repair nowcast missed by 0.98%. The renter estimate accounted for most of the committed nowcast's error.

## Known approximations

The CE replication remains approximate in four known ways:

- It deflates each interview with an annual-average FCSUti CPI keyed to collection year rather than BLS's quarterly treatment of the terminal Q1.
- It applies the 80% food allocation to the combined FMLI `GROCER` summary rather than UCC 790210 alone.
- It omits home-internet expenditures because FMLI has no matching summary.
- It omits BLS's in-kind imputations for broadband, LIHEAP, NSLP, WIC, and rental assistance.

These are deferred to the 2026-method issue and are not changed in this correction branch. Separately, the bundled metro geographic adjustments still derive from the pre-correction Census metro workbook; composed metro thresholds rescale that workbook onto the corrected national base until Census re-releases it.

## Projecting thresholds past the published years

BLS does not age thresholds by a price index — each year is re-estimated from the rolling five-year CE window, so the published series moves with consumption as well as prices. We backtested four executable projection rules over 2020–2024, standing at each year's corrected prior-year base and scoring against the corrected actual (`scripts/backtest_threshold_projection.py`). The tracked result, including annual errors and input provenance, is `spm_calculator/data/nowcast/backtest_2020_2024.json`.

| Rule | Mean abs error/yr | Worst year |
|---|---|---|
| All-Items CPI-U aging (status quo in policyengine-us) | 2.23% | 3.99% (2023) |
| FCSUti-composite CPI aging (realized) | 1.57% | 2.59% (2024) |
| CE replication growth ratio | **0.41%** | **0.65% (2020)** |
| 50/50 blend of the last two | 0.76% | 1.39% (2023) |

The price-aging rules were generally below the corrected actuals in the later backtest years because prices alone do not capture real FCSUti consumption growth or in-kind benefit changes. The CPI rules use realized index values; a true forward forecast would also carry CPI-forecast error (2022's CPI surprise was ~5 points), which the replication ratio avoids because CE microdata for a nowcast year is published before BLS's thresholds for that year. The repaired backtest ranks replication first; the blend remains the committed 2025 method because it was selected before that repair, and reselecting on a second look at five years would select on noise.

The packaged **2025 nowcast** (`nowcast_thresholds(2025)`, `spm_calculator/data/nowcast/nowcast_2025.json`) applies the blend to the corrected 2024 base:

| Tenure | Replication ratio | FCSUti CPI ratio | Blend | Nowcast 2025 |
|---|---|---|---|---|
| Owner w/ mortgage | 1.0599 | 1.0321 | 1.0460 | $41,036.34 |
| Owner w/o mortgage | 1.0443 | 1.0321 | 1.0382 | $34,135.99 |
| Renter | 1.0462 | 1.0321 | 1.0392 | $40,755.98 |

Two data notes. 2025 CPI annual averages are 11-month means — BLS canceled the October 2025 CPI release during the federal shutdown. And computing the replicated 2025 threshold surfaced one more schema break: from the 2024Q2 files, CE replaces the `FOOD`/`FDHOME` summaries with `GROCER` (all grocery purchases, food and nonfood); food at home is 80% of `GROCER` per the BLS errata, the same allocation BLS uses for the official thresholds. Before the per-row vintage-aware construction, pooled windows silently zeroed food for redesign-era quarters and replicated 2025 thresholds *fell* 4–5% nominal — the same silent-schema-drift failure class as everything else on this page.

BLS published the actual 2025 thresholds on August 24, 2026. `nowcast_thresholds(2025)` deliberately preserves the table above for evaluation, emits a warning, and directs current calculations to `get_thresholds(2025)`.
