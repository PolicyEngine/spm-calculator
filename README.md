# spm-calculator

Calculate [Supplemental Poverty Measure (SPM)](https://www.census.gov/topics/income-poverty/supplemental-poverty-measure.html) thresholds from a pinned statistical release, with standalone lookup, reproducible estimation and optional model adapters.

[![Try the Calculator](https://img.shields.io/badge/Try-Calculator-teal)](https://spm-calculator.vercel.app/)
[![Documentation](https://img.shields.io/badge/docs-github-green)](https://github.com/PolicyEngine/spm-calculator/tree/main/docs)

## Interactive Calculator

**[Try the SPM Threshold Calculator](https://spm-calculator.vercel.app/)** - A browser-based calculator for metros, states, counties, and congressional districts, with a direct handoff to the Python package for tract-level and batch work.

The rebuilt calculator runs entirely in your browser. National thresholds through published 2025, Census 2024 metro rent indices, and ACS 2023 state, county and district rents are bundled with an explicit release hash. No browser credential or Census request is required. Housing shares are fixed to 2024 and identified as carried approximations for other years.

This branch is an **unpublished 0.5.0 rebuild**. The public calculator remains on its existing deployment until a separate production promotion. The corrected national series changes some legacy numerical outputs; see [compatibility and rollout](docs/spm-releases.md#compatibility-and-rollout).

### Run Locally

**Next.js app (recommended):**
```bash
cd web
bun install --frozen-lockfile
bun run dev
```

Generate and check browser inputs with `uv run scripts/export_web_release.py` and `uv run scripts/export_web_release.py --check`.

## Overview

The SPM threshold is calculated as:

```
threshold = base_threshold[tenure] × equivalence_scale × geoadj[tenure]
```

Where:
- **base_threshold** varies by housing tenure (renter, owner with mortgage, owner without mortgage), calculated from 5-year rolling Consumer Expenditure Survey data
- **equivalence_scale** adjusts for family composition using the official Betson three-parameter SPM scale
- **geoadj** adjusts for local housing costs, using official Census metro thresholds where available and a tenure-specific ACS rent adjustment elsewhere

## Installation

```bash
pip install spm-calculator
```

## Quick Start

For new integrations, select an immutable release. This path performs no network requests and does not import PE, Microcosm or Axiom:

```python
from spm_calculator import load_release, SPMUnit

release = load_release()  # A fixed bundled artifact, not "latest" over the network.
print(release.release_id, release.content_sha256)
result = release.calculate_unit(SPMUnit(
    unit_id="family-1", num_adults=2, num_children=2,
    tenure="renter", year=2025,
    geography_kind="county", geography_id="06001",
))
print(result["threshold"], result["provenance"])
```

Save the content hash and supply `expected_sha256=` to `load_release` on replay. The CLI supports `info`, `verify`, `calculate` and `export --format csv`. Unsupported years fail; new projections require explicitly identified inputs and methods. See [release contract and integration boundaries](docs/spm-releases.md), [current CE replication](docs/current-ce-replication.md), [PE integration](docs/policyengine-release-integration.md), and [Axiom integration](docs/axiom-integration.md).

The existing calculator API remains available for legacy callers:

```python
from spm_calculator import SPMCalculator

# Initialize calculator for a specific year
calc = SPMCalculator(year=2024)

# Get base thresholds by tenure (national, before geographic adjustment)
base = calc.get_base_thresholds()
# {'renter': 39219.89, 'owner_with_mortgage': 39231.0, 'owner_without_mortgage': 32878.59}

# Get GEOADJ for a specific location
geoadj = calc.get_geoadj("metro_area", "35620", tenure="renter")  # New York metro
# 1.1599

# Calculate threshold for a specific family in a specific location
threshold = calc.calculate_threshold(
    num_adults=2,
    num_children=2,
    tenure="renter",
    geography_type="metro_area",
    geography_id="35620"
)
# A composition of the selected national series and pinned metro adjustment.
```

Official metro thresholds are bundled with the package. For custom ACS-based
geographies like states, counties, congressional districts, PUMAs, and tracts,
set `CENSUS_API_KEY` to fetch current median rents.

### SPM unit IDs

If your data does not already include Census SPM resource-unit IDs, use
`spm_unit_id` to create person-level IDs before calculating thresholds:

```python
from spm_calculator import spm_unit_id

ids, diagnostics = spm_unit_id(persons, diagnostics=True)
```

The function preserves native `person_spm_unit_id`, `spm_unit_id`, or `SPM_ID`
columns when present. Otherwise, it reconstructs units from the smallest
available person-level inputs:

| Input class | Columns recognized by default |
|-------------|-------------------------------|
| Required | `household_id`, `person_household_id`, `H_SEQ`, or `PH_SEQ` |
| Strongly recommended | `family_id`, `person_family_id`, or `PF_SEQ`; `age` or `A_AGE` |
| Person pointers | `line_number`, `person_line_number`, or `A_LINENO`; `parent_id`, `mother_id`, `father_id`, `PEPAR1`, `PEPAR2`; `spouse_id` or `A_SPOUSE`; `unmarried_partner_id`, `partner_id`, `cohabiting_partner_id`, or `PECOHAB` |
| Census SPM assignment flags | `SPM_WFOSTER22`, `SPM_WUI_LT15`, and `SPM_WNEWPARENT`; `SPM_WCOHABIT` is used only when no direct cohabiting partner pointer such as `PECOHAB` is available |
| Generic fallback flags | `relationship_to_head`, `family_relationship`, or `A_FAMREL`; `is_foster_child` or `foster_child` |

Diagnostics describe assignment provenance and missing recommended inputs; they
do not summarize the resulting unit distribution.

For parity checks against Census/native IDs or published thresholds:

```python
from spm_calculator import spm_threshold_match, spm_unit_id_match

id_report = spm_unit_id_match(persons)
threshold_report = spm_threshold_match(calculated, reference, atol=1.0)
```

The optional ASEC parity tests run against a real Census CPS ASEC HDFStore when
`SPM_CALCULATOR_ASEC_H5=/path/to/census_cps_2024.h5` is set.

## Supported Geographies

- `nation` - National average
- `state` - 50 states + DC
- `county` - ~3,200 counties
- `metro_area` - Metropolitan statistical areas
- `congressional_district` - 435 congressional districts
- `puma` - Public Use Microdata Areas
- `tract` - Census tracts (limited availability)

## Data Sources

- **Base thresholds**: [BLS Consumer Expenditure Survey](https://www.bls.gov/cex/) - 5-year rolling FCSUti (Food, Clothing, Shelter, Utilities, telephone, internet)
- **Geographic adjustment**: [ACS 5-Year Estimates](https://www.census.gov/programs-surveys/acs) - Table B25031 (Median Gross Rent by Bedrooms)
- **Methodology**: [Census SPM Technical Documentation](https://www2.census.gov/programs-surveys/supplemental-poverty-measure/datasets/spm/spm_techdoc.pdf)

## Methodology

### Base Threshold Calculation

Following BLS methodology (updated September 2021, corrected July 17, 2026):
1. Load CE Interview PUMD collection quarters (T−5)Q2 through (T)Q1 for target year T (cached year bundles)
2. Filter to consumer units with children
3. Calculate FCSUti expenditures (shelter includes owner mortgage-principal outlays; UTIL already contains telephone)
4. Convert to reference family (2 adults, 2 children) using equivalence scale
5. Apply the BLS formula over the 47th-53rd percentile estimation sample: `0.82 × (1.2 × FCSUti_E − SU_E + SU_Eh)` (82% anchor since the 2026 correction; 83% before)

### Geographic Adjustment (GEOADJ)

For official public metro areas, the package uses the published Census metro table directly.

For custom geographies built from ACS rents, the adjustment is tenure-specific:
```
GEOADJ_t = (local_median_rent / national_median_rent) × housing_share_t + (1 - housing_share_t)
```

For 2024 thresholds, the tenure-specific housing shares are:
- `0.443` for renters
- `0.434` for owners with a mortgage
- `0.323` for owners without a mortgage

### Equivalence Scale

The SPM uses the official Betson three-parameter scale:
- Single adult with children: `(1 + 0.8 + 0.5 × (children - 1))^0.7`
- Multiple adults with children: `(adults + 0.5 × children)^0.7`
- One adult without children: `1.0`
- Two adults without children: `1.41`
- Three or more adults without children: `adults^0.7`
- Normalized to the reference family `(2 adults, 2 children) = 3^0.7`

## Data provenance and validation

Packaged thresholds come from the official BLS workbook (bundled with recorded SHA-256, parsed by `scripts/build_threshold_series.py` — never hand-edited). Three series ship with the package:

- `bls-corrected-2026-07-17` (default): the corrected series BLS published on July 17, 2026, spliced to BLS's published 2025 continuation from the current workbook; full precision, 2005-2025, with standard errors and tenure shares
- `census-published-pre-correction`: what every published 2019-2024 SPM statistic used, cross-verified against the Census P60 reports
- `package-legacy-0.3`: values shipped in spm-calculator ≤ 0.3.1, retained for reproducibility (2019-2023 contained hand-entry errors of up to 8% — see [docs/bls-2026-correction.md](docs/bls-2026-correction.md))

| Tenure | 2024 corrected BLS | Package |
|--------|--------------------|---------|
| Renter | $39,219.89 | $39,219.89 |
| Owner w/ mortgage | $39,231.00 | $39,231.00 |
| Owner w/o mortgage | $32,878.59 | $32,878.59 |

The full-precision BLS 2025 thresholds are $41,322.71 for owners with mortgages, $34,326.00 for owners without mortgages, and $41,700.56 for renters. The BLS publication page displays these as $41,323, $34,326, and $41,701.

A weekly [drift-watch CI job](.github/workflows/bls-drift-watch.yaml) checks the frozen correction workbook, BLS's current workbook, and the rounded 2025 page table, opening an issue if the packaged series diverges. `get_thresholds(2025)` now returns published BLS values. The superseded `nowcast_thresholds(2025)` remains available as a historical forecasting commitment and warns callers to use the published series; its realized mean absolute error was 1.17%. The four-rule 2020-2024 backtest and the 2025 evaluation are recorded in [docs/bls-2026-correction.md](docs/bls-2026-correction.md). The independent CE-PUMD replication reproduces official threshold levels within 1-4.5% (without the in-kind benefit imputations); measured fidelity by year is documented there as well.

Official metro thresholds are validated against [Census SPM Thresholds by Metro Area: 2024](https://www2.census.gov/programs-surveys/demo/tables/p60/287/SPM-pov-threshold-2024.xlsx) (pre-correction vintage; composed metro thresholds rescale onto the corrected national base until Census re-releases the workbook).

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

Contributions welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
