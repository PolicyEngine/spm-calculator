# Geography and county assignment

The canonical forecast stores an SPM estimation-area menu for each target year.
A county is a lookup input assigning a unit to one of those areas; the calculator
does not estimate a county-specific threshold from the county's median rent.

## Resolve a county for its year

```python
from spm_calculator import SPMUnit, load_forecast

forecast = load_forecast()
assignment = forecast.resolve_county(
    2025, "06037", county_vintage="2020", scenario="ce_trend"
)
print(assignment["kind"], assignment["area_id"])  # metro 31080
result = forecast.calculate_unit(
    SPMUnit(
        "synthetic-la", 2, 2, "renter", 2025,
        geography_kind=assignment["kind"], geography_id=assignment["area_id"],
    ),
    scenario="ce_trend",
)
print(result["provenance"]["geography"])
```

County FIPS must be a five-digit string, including leading zeroes.
`county_vintage="2020"` describes the county identifiers; it does not mean that
the selected target year's rent inputs are from 2020. The returned assignment
contains `area_id`, `kind`, `county_fips`, `county_vintage`, `boundary_vintage`,
`assignment_method`, `assignment_sha256` and `status`. Its `research_assignment`
status describes the mapping, separately from the area's rent status.

Assignments can change between years. For example, the artifact records
Sumter County, South Carolina (`45085`) moving from a published residual area
in 2022 to a modeled residual area in 2023. Do not interpret that level change
as estimated annual rent growth; inspect the recorded series-break metadata.

## Inspect actual areas and statuses

```python
from spm_calculator import load_forecast

forecast = load_forecast()
areas = forecast.areas_for_year(2025)
for area_id in ("31080", "1002"):
    area = areas[area_id]
    print(area_id, area["name"], area["area_type"], area["status"])
    print("Official published area:", area["official_published_area"])

geography = forecast.geography_factor(
    2025, "renter", kind="metro", geoid="31080"
)
print(geography["factor"], geography["rent_index"], geography["diagnostics"])
```

The API kind `metro` includes these `area_type` values:

| `area_type` | Meaning |
| --- | --- |
| `msa` | Named metropolitan statistical area. |
| `state_metro_residual` | Published state residual metro area. |
| `state_nonmetro` | Published state nonmetro area. |
| `modeled_residual_metro` | Explicit modeled residual metro area without an official published area anchor. |

A state residual area is not an entire-state estimate. An
`official_published_area=True` identifies an official area anchor; it does not
establish that a future target year's rent index is published. Consult that
area's `status`, `anchor_status`, `source_ids`, diagnostic flags and any
`series_breaks`. The entry-wide `geography_status` may be `mixed` and must not
replace the selected area's status.

## Explicit national geography

```python
from spm_calculator import SPMUnit, load_forecast

forecast = load_forecast()
result = forecast.calculate_unit(
    SPMUnit("national-reference", 2, 2, "renter", 2026,
            geography_kind="national")
)
assert result["geographic_factor"] == 1.0
assert result["geography_status"] == "explicit_national"
```

National takes no area ID. The CLI requires `--national`, `--area` or `--county`;
the provider and Frame default to county assignment unless a location mode is
explicitly selected. Unknown areas/counties never silently become national.

## Housing adjustment

For a selected year's rent index `r` and tenure housing share `s`:

```text
geographic_factor = 1 + s × (r − 1)
unadjusted_threshold = national_reference_threshold × equivalence_factor
threshold = unadjusted_threshold × geographic_factor
housing_portion = unadjusted_threshold × (geographic_factor + s − 1)
```

Use the selected year's shares and rents together. Old yearless rent/share
helpers and custom state/district/PUMA/tract APIs do not define this forecast's
geography contract. Source allocation and finite donor support are documented
in [rolling forecasts](../rolling-forecasts.md).
