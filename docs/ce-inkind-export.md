# CE in-kind imputations by interview

We publish the [in-kind imputation](ce-inkind-imputation.md) for every CE
Interview record it covers: one row per FMLI record (`NEWID`) per implicate,
for every interview in the 44 quarterly FMLI files it reads, one per quarter
from 2014Q2 to 2025Q1 (reference years 2014–2024). That is 242,295
interviews × 5 implicates = 1,211,475 rows. For 2015Q1 it reads `intrvw14`'s
`fmli151.csv`, so interviews found only in `intrvw15`'s `fmli151x.csv` are
not in the file (see [merging](#merging-with-the-ce-public-use-files)).

Each row carries a participation flag and an annual dollar amount for school
lunch, WIC, LIHEAP, broadband subsidies and rental assistance. We impute
broadband only from reference year 2022, so before then its flag is empty
and its amount zero. The export script reruns the imputation with the
settings and inputs of the replication receipt
`spm_calculator/data/current/ce_inkind_replication_2019_2025.json`. It stops
unless the CE and CPS ASEC file hashes and the imputation settings match the
receipt's and the rerun reproduces the receipt's imputation diagnostics.

The values follow the rules the replication applies to approximate BLS's SPM
thresholds, not what each consumer unit received. Read
[where the values follow rules](#where-the-values-follow-rules-not-receipt)
before using them.

## Download

We publish the files below as assets of the GitHub release
[`ce-inkind-by-interview-v1`](https://github.com/PolicyEngine/spm-calculator/releases/tag/ce-inkind-by-interview-v1),
built from the commit that adds this page to `main`.
[Regenerate](#regenerate) describes how to build them yourself.

| File | Contents |
|---|---|
| `ce_inkind_by_interview_2014q2_2025q1.csv.gz` | The export, gzipped CSV (4.5 MB compressed, 71 MB uncompressed) |
| `ce_inkind_by_interview_dictionary.csv` | The column table below |
| `ce_inkind_by_interview_manifest.json` | Counts by reference year, source files and hashes, settings, participant counts and the results of the script's checks; the script writes it only after every check passes |
| `README.md` | A short description that points here |
| `SHA256SUMS` | SHA-256 hashes of the other files |

The release is licensed CC BY 4.0. It uses the BLS Consumer Expenditure
Survey Interview public-use microdata, the Census Bureau's CPS ASEC
public-use files and official poverty thresholds, USDA FNS school lunch
rates and WIC EBT dates, and WIC
state food costs from the U.S. Census Bureau SPM team, compiled from USDA FNS
WIC program data (personal communication, November 16, 2026).

## Merging with the CE public-use files

- Join on `NEWID` as a number. The 2014 release writes `NEWID` as a 7-digit
  integer and the 2015–2024 releases as an 8-character zero-padded string,
  so a text join misses matches.
- `NEWID` is unique across every interview in the file. `ce_year` and
  `ce_quarter` give the collection year and quarter, so you can confirm that
  you joined the right quarter. They cannot tell a quarter 1 file from the
  next release's overlap file, which carries the same year and quarter; the
  manifest's `ce_sources` names the release and file the imputation read for
  each quarter.
- Quarter 1 of year Y comes from the year Y−1 release (`fmliYY1.csv`), not
  from the year Y release's overlap file (`fmliYY1x.csv`). For 2016–2019 and
  2024, the overlap file holds the same interviews, but some income and
  reference-person age values differ from the ones the imputation read. For
  2015, `intrvw15`'s `fmli151x.csv` holds a partly different set of
  interviews with different weights: it shares 2,721 interviews with
  `intrvw14`'s `fmli151.csv` and has 1,482 of its own. Use `intrvw14`'s
  `fmli151.csv`.
- Apart from `NEWID`, the file copies no CE variables and holds no weights.
  Two columns recode CE responses rather than model them:
  `rental_assistance_participant` (tenure and the rent file's subsidy items)
  and `wic_broad_universe_only` (members' ages and sexes). Take `FINLWT21`,
  the replicate weights and any other CE variables from FMLI.
- Each implicate holds every interview once. To analyze one implicate, keep
  its rows and merge them one-to-one onto FMLI by `NEWID`. The unfiltered
  file has five rows per interview and merges many-to-one.

## Columns

| Column | Type | Description |
|---|---|---|
| `NEWID` | integer | CE Interview FMLI record id. Unique across every row of one implicate; join on it as a number. |
| `implicate` | integer | Implicate number, 1 to 5 (the receipts' index plus 1). Analyze each implicate separately and combine estimates with Rubin's rules. Do not pair implicate m with the CE income imputation FINCBTXm: each CE unit's poverty ratio uses FINCBTXM, the mean of the five. |
| `ce_year` | integer | Collection year of the interview: the year in the FMLI file name (fmliYYq.csv). Quarter 1 files ship in the previous year's release. |
| `ce_quarter` | integer | Collection quarter of the interview, 1 to 4: the quarter in the FMLI file name. |
| `reference_year` | integer | Year whose program rules, CPS ASEC donors and dollars the values use: ce_year for quarters 2-4 and ce_year - 1 for quarter 1. |
| `wic_broad_universe_only` | 0/1 | 1 if the unit has a child under 5 but no woman aged 15 or older. BLS's WIC universe adds these units from the 2025 thresholds; the WIC columns here leave them out. |
| `nslp_participant` | 0/1 | 1 if the imputation assigns free or reduced-price school lunch, the outcome CPS ASEC households report in HFLUNCH. Paid lunches never count as participation. Only units with a member aged 5-18 can be 1. |
| `nslp_amount` | dollars | Annual school lunch value, in nominal dollars of the reference year: a matched CPS ASEC household's value, scaled to the unit's children aged 5-18. For 2014-2017 the donor value covers free and reduced-price lunches; from 2018 it is Census's SPM_SCHLUNCH summed over the donor household's SPM units, which can include paid lunches for the donor's other children. |
| `wic_participant` | 0/1 | 1 if modeled as receiving WIC. Only units with a woman aged 15-45, or with a child under 5 and a woman aged 15 or older, can be 1. |
| `wic_amount` | dollars | Annual WIC food value, in nominal dollars of the reference year: Census's participant count x 12 x the state's average monthly food cost per person. Where the CE withholds the state, the cost is the weighted mean for known-state units in the unit's region and quarter whose state had not finished WIC EBT. Zero where the state had finished statewide WIC EBT and in every reference year from 2020. |
| `liheap_participant` | 0/1 | 1 if modeled as receiving energy assistance. Any unit can be 1. |
| `liheap_amount` | dollars | Annual energy assistance, in nominal dollars of the reference year: a matched CPS ASEC recipient's reported amount. |
| `broadband_participant` | 0/1 or empty | 1 if modeled as receiving a broadband subsidy. Empty before reference year 2022, when the subsidy is not modeled. |
| `broadband_amount` | dollars | Annual broadband subsidy, in nominal dollars of the reference year: a matched CPS ASEC household's Census-assigned EBB or ACP value. Zero before reference year 2022. |
| `rental_assistance_participant` | 0/1 | 1 if the unit rents and reports government-subsidized or public housing in the CE rent file. The same in every implicate. |
| `rental_assistance_amount` | dollars | Annual rental assistance, in nominal dollars of the reference year: 12 x (imputed market rent - rent paid). |

Amounts are rounded to cents.

## Where the values follow rules, not receipt

**Participation is modeled.** Apart from rental assistance, each flag is a
draw from a logit fit on CPS ASEC households, so it follows that model's
predicted participation for the unit's covariates, not what the unit
received. A zero means the imputation assigned
nothing under these rules, not that the unit reported none. Components are
drawn independently given the shared covariates, so joint receipt, such as
WIC with school lunch, follows only from those covariates.

**Each interview gets its own draws.** Every unit-level draw hashes the
interview's `NEWID`, and the covariates come from that interview's records.
One consumer unit's interviews (`NEWID` is the CE's `CUID` × 10 plus the
interview number) can therefore differ in participation and amount even when
nothing about the unit changed.

**Amounts are annual, in nominal dollars of the reference year.** An
interview reports three months of spending. To set an amount beside one
interview's quarterly spending (`*PQ + *CQ`), divide it by 4. The threshold
stage adds the annual amount to four times quarterly spending and inflates
it by collection year.

**Reference year.** A quarter 2–4 interview carries its collection year and
a quarter 1 interview the year before, so a March interview carries the
previous reference year. Program rules, CPS ASEC donors, WIC food costs and
school lunch values follow the reference year, with one exception: before
reference year 2020, we test each state's WIC EBT date against the middle of
the three months the interview covers, which for a March interview is
mid-January, after its reference year ends.

**School lunch.** The imputation assigns free or reduced-price lunch, the
outcome CPS households report in `HFLUNCH`. Paid lunches never count as
participation, and a universal free lunch counts only where CPS respondents
report it under that question. Census's `SPM_SCHLUNCH` also values lunches
for CPS households that report no free or reduced-price lunch; the
imputation leaves those households out. Any unit with a member aged 5–18 can participate; there is no
enrollment test. A participating unit takes a matched CPS household's
value, scaled to the unit's number of children aged 5–18. For reference
years 2014–2017 that value comes from the USDA formula and covers free and
reduced-price lunches only. From 2018 we use Census's `SPM_SCHLUNCH`, summed
over the donor household's SPM units, which can include paid lunches for the
donor's other children. It also carries Census's COVID-era methods, P-EBT, universal free
meal and summer EBT rules, and its fall 2022 method from reference year
2023; BLS says it uses the traditional method before and after the COVID-19
period. In reference year 2020, some participating CPS households carry a
zero Census value, so 528–557 interviews modeled as participants get \$0,
depending on the implicate.

**WIC.** BLS adds WIC only where a state had not fully implemented WIC EBT.
For reference years before 2020, we add WIC to a unit only if its state's
statewide EBT date, from FNS's December 2022 WIC EBT status report, falls
after the middle of the three months the interview covers; from reference
year 2020 we add no WIC in any state. So `wic_amount` is zero
from 2020, and earlier once the unit's state had finished, even when
`wic_participant` is 1. In each implicate, 220–335 participants a year get
\$0 in 2014–2019, and every participant, 319–424 a year, from 2020.

Where the CE withholds the state, a draw sets whether the state had
finished, from the share of known-state units in the same region and quarter
whose state had. A unit drawn as not finished takes the weighted mean food
cost of the known-state units in that cell whose state had not finished. A unit
whose region is also withheld gets no WIC. The value is food cost only:
Census's participant count (every child under 5, plus the mother of a child
aged 0–1, otherwise one pregnant woman; we count the mother only when the
unit has a woman aged 15 or older) × 12 × the state's average monthly food cost per person, by fiscal
year numbered like the reference year.

**WIC universe.** BLS's WIC universe is a woman aged 15–45, or a child under
5 with a woman aged 15 or older. From its 2025 thresholds BLS adds units
with a child under 5 but no woman aged 15 or older. The WIC columns apply
the first rule, as this replication does for every target before 2025;
units that only the 2025 rule adds carry `wic_broad_universe_only` = 1 and
zero WIC here. Thresholds from 2025 on draw only on reference years 2020 and
later, where our 2020 cutoff sets every WIC amount to zero, so the WIC
amounts in the file are the ones every threshold in this replication used.

**Broadband.** BLS adds broadband subsidies from the 2023 thresholds, with
data from 2022, so we impute them from reference year 2022. Before that,
`broadband_participant` is empty and the amount zero; Census values the
Emergency Broadband Benefit from reference year 2021. Any unit can
participate. The amount is a matched CPS household's subsidy as Census
assigns it (`SPM_BBSUBVAL`), not a reported amount.

**LIHEAP.** Any unit can participate, with no income, tenure or utility
screen. The amount is a matched CPS recipient's reported energy assistance
(`HENGVAL`), which may include assistance other than LIHEAP.

**Rental assistance.** Participation comes from the CE: a renter whose rent
file records government-subsidized rent (`GOVTCOST`) or public housing
(`PUBLHOUS`). It is the same in every implicate, and owners and units outside
the rent file get zero. The amount is 12 × (a draw of market rent above the
rent paid − the rent paid), from a Tobit fit on that reference year's CE
renters. The draw has no cap, so a few amounts are large: in each implicate,
37–57 of the 11,357 participating interviews get more than \$50,000 a year,
and the largest amount is about \$114,000.

**Every interview, not only the threshold sample.** The file covers every
interview in the files it reads, including the units the threshold replication
drops (units without children under 18, tenure codes 5 and 6, and minor-only
units). Those units' values never entered a threshold.

## Implicates

Analyze each implicate on its own and combine the estimates by Rubin's
rules, as the [sampling uncertainty](ce-inkind-imputation.md#sampling-uncertainty)
section does; averaging a unit's amounts across implicates understates the
variance and turns participation into fractions. The five in-kind implicates
do not line up with the CE's five income imputations: each CE unit's
poverty ratio uses `FINCBTXM`, their mean, and no model reads the five
separately. Rental assistance participation,
the WIC EBT draw for units whose state the CE withholds, and the
free-or-reduced draw in the school lunch formula years are the same in every
implicate, and the spread across implicates leaves out the CPS ASEC donor
pools' sampling error.

## Regenerate

The script reads only cached files. Fetch the CE Interview bundles for
2014–2024 with `spm_calculator.ce_threshold.download_ce_bundle(year)`, and
put the CPS ASEC files that `spm_calculator.cps_asec.source_files(year)` lists
for survey years 2015–2025, from `cps_asec.source_url(year, name)`, in the
CPS cache (`~/.cache/spm-calculator/cps-asec`). The manifest lists every
file's URL and SHA-256. Then run:

```bash
uv run --no-sync python scripts/export_ce_inkind_by_interview.py --out <directory>
```

The script makes no network requests and takes about a minute and 2 GB of
memory. It reads the same quarters as the replication receipt and stops
unless:

- every quarter comes from the release the receipt used, never an overlap
  file, and every bundle and CPS ASEC file matches the receipt's hash;
- the imputation's settings equal the receipt's, it imputes every
  component, and its diagnostics match the receipt's, counts exactly and
  other values to a relative 10⁻⁹;
- the recorded participation draws give the imputation's own participation
  rates, every positive amount has a participant, and LIHEAP and broadband
  participation equals a positive amount;
- the written file, read back with pandas defaults, has every key and flag
  equal to the imputation's, as integers, except `broadband_participant`,
  which reads back as floats and is empty exactly where the reference year
  is before 2022; every flag 0 or 1 where present, every amount finite, in
  whole cents and within half a cent of the imputation's, and every
  interview once per implicate.

Rerunning with the same inputs, code and Python environment gives the same
CSV byte for byte, and the manifest records its hash. Other builds of NumPy
or SciPy can move rental assistance values in their last bits, which
rounding to cents almost always hides, so compare a rerun with the published
file by value, to the cent, rather than by hash. Impute every quarter in one
call, as the script does: the WIC fallback for withheld states and the rent
model draw on all the interviews of a quarter or reference year, so imputing
a subset changes some values.

`spm_calculator.ce_inkind.impute_in_kind` returns amounts, not participation.
`spm_calculator.ce_inkind_export.observe_participation` records the draws
while it runs, returns each draw unchanged and draws no random numbers.
`export_frames` builds the rows and runs the participation checks. The
script checks the sources, settings and diagnostics before it calls
`export_frames`, and `verify_written` reads the written file back and checks
it.

## Not covered

Interviews collected from 2025Q2 on are not in the file. Adding them needs
the 2025 CE release, the 2026 CPS ASEC (the donor households for reference
year 2025), and at least two parameter updates the imputation stops
without: the 2025 official poverty thresholds and the 2025–26 school lunch
rates. The export
script reads only the replication receipt's quarters and stops unless its
run matches that receipt, so it would also need a new receipt.
