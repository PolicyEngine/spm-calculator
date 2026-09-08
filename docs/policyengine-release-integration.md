# PolicyEngine release integration

The explicit-release adapter replaces the national threshold, equivalence-scale
application, geographic adjustment and housing portion in one PolicyEngine
simulation. The housing portion caps counted housing assistance and therefore
also changes SPM resources. It uses the same release data as the standalone
calculator; taxes and other benefits continue to run in the country model.

This first integration requires the accompanying **development changes** in
`PolicyEngine/policyengine.py`. The published wrapper does not yet accept
`spm_release`. These checks do not certify a population-data bundle or complete
the migration of US household rules to Axiom.

## Public wrapper

With the accompanying wrapper installed:

```python
import policyengine as pe

selection = pe.us.SPMReleaseSelection(
    # Omit path to explicitly select the installed SPM package's bundle.
    path="my-reviewed-spm-release.json",
    expected_sha256="<the release's independently retained 64-character digest>",
    year_policy="pe_cpi_u",
    geography_kind="congressional_district",
)
result = pe.us.calculate_household(
    people=[{"age": 40}, {"age": 40}, {"age": 8}, {"age": 5}],
    spm_unit={"spm_unit_tenure_type": "RENTER"},
    household={"state_code": "AL", "congressional_district_geoid": 101},
    year=2025,
    spm_release=selection,
    extra_variables=[
        "spm_unit_spm_threshold",
        "spm_unit_spm_threshold_housing_portion",
        "spm_unit_capped_housing_subsidy",
    ],
)
print(result.spm_unit.spm_unit_spm_threshold)
print(result.provenance["spm"])
```

The selection accepts a JSON mapping as well as a Pydantic object. External
files require an expected content hash. The provider checks the hash and takes
an immutable snapshot before constructing simulation-specific formulas. Two
simulations can use different releases in the same process. Returning or
modifying a provenance dictionary cannot change the formula snapshot.

Omitting `spm_release` preserves the country's existing threshold path. That
legacy path still uses its fixed housing-share imports, its CPI-U uprating and
its implicit national geographic fallback. Updating the installed package
changes the legacy reference table to corrected values, but does not migrate
those other behaviors to this adapter.

## Year selection and housing shares

| Target entry | Explicit provider behavior |
| --- | --- |
| Published | Use the release entry. |
| Nowcast or forecast, `allow_estimated=True` | Use the release estimate. |
| Estimate declined or entry absent, `year_policy="error"` | Raise an error. |
| Estimate declined or entry absent, `year_policy="pe_cpi_u"`, after the latest published year | Extrapolate the latest published base using the evaluated PE CPI-U ratio. |
| Missing past/interior year | Raise an error; never backcast. |

The PE compatibility provider defaults to `pe_cpi_u`. This differs from the
standalone release reader, which errors for absent years. PE extrapolation is
labeled `consumer_extrapolation`, carries no estimated uncertainty interval,
and emits a warning when a target year is first evaluated. Python warning
filters still apply. Its receipt includes the base and target endpoint dates,
values, ratio, parameter identity and actual model/core versions. Endpoint
classification remains explicitly unknown when model metadata does not establish
whether a value is observed or projected. It is not described as observed CPI.

A declined release estimate remains visible in `unused_release_estimate`.
Extrapolation carries the published base's housing shares, including their
source and reference year. The first bundle uses the legacy 2024 shares where
year-specific shares are unavailable, with explicit carried-value provenance.
The legacy year-less `get_housing_share` values remain 0.434, 0.323 and 0.443 for
owners with mortgages, owners without mortgages and renters, respectively.
Tests with different shares use synthetic fixtures, not invented official data.

## Geography and input ownership

Select `national` explicitly, a pinned `metro` identifier, or
`congressional_district`. The latter can take a fixed `geography_id` or use
each SPM unit's containing household district. The release supplies the actual
geography vintage. Unknown requested areas error unless
`missing_geography="national"` was selected; that fallback remains in the
provenance receipt with the requested identifier and reason.

For an observed Census whole-threshold factor, use `geography_kind="explicit"`,
`geographic_adjustment=<factor>` and `geography_vintage=<source/vintage>`.
The factor must be finite, positive, and consistent with a nonnegative housing
portion. It is not a raw local-to-national rent ratio.

The provider owns the threshold chain and derived housing cap. Its input check
rejects baked threshold outputs, computed counts, capped housing subsidy,
SPM net income and poverty outputs. Keep observed Census values under separate
report-only names. The check never reconstructs or rewrites supplied native SPM
unit IDs or membership. Existing PE `is_adult`/`is_child` formulas still classify
members; exact Census independent-teen classification is not established here.

The population input audit identified an existing path that loads saved
thresholds as model inputs and an AGI-based uprating override for that saved
column. Household acceptance and the small multiple-unit input-contract fixture
do not prove those production datasets have migrated. Population adoption must
audit source columns and remove formula-owned outputs from the simulation input
contract while preserving the reported values separately.

## Development model registration

The wrapper's certified model pin can differ from the development country
checkout. In that case ordinary wrapper import can fail its population-data
compatibility check. For these household-only integration checks, set
`POLICYENGINE_US_HOUSEHOLD_ONLY=1` **before importing PolicyEngine**. This explicit
mode registers the installed country's actual variables and parameters but
attaches no certified data manifest or certification. Population run/load/save,
managed microsimulation and certified TRACE export are unavailable in this
mode. The certified manifests remain unchanged.

The checked development combination is Python 3.14.4, `policyengine` 5.3.0
with the accompanying wrapper changes, `policyengine-us` 1.824.3,
`policyengine-core` 3.30.2 and the accompanying SPM package. Install the bare
wrapper plus the exact selected development dependencies; its `[us]` extra
pins an older certified country/core pair. The final integration receipt
records the actual SPM version/content hash and all source commit identities.

The explicit provider rejects nonintegral or negative unit counts and units
without a classified SPM adult. Minor-only units need a separate classification
decision; they do not receive a zero threshold. Legacy formulas outside the
provider retain their existing behavior.
