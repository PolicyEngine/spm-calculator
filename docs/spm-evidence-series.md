# SPM evidence series: plan

PolicyEngine's SPM poverty rate differs from Census's for several reasons at
once: PolicyEngine computes taxes, tax units and benefits with its own
rules, imputes inputs those rules need, and reweights the records. This
series measures each reason on its own. Every step starts from the previous
step's results, swaps one Census piece for PolicyEngine's, and reports how
the SPM rate, the Table 5 element effects and the Table 4 rows move.

[Step 1](census-spm-reproduction.md) rebuilt Census's published 2025
estimates from the 2026 CPS ASEC public-use file. This plan describes steps
2 to 6. None of them has run yet, and no number below comes from them.

## Rules for every step

- **Same records, same weights, through step 5.** Steps 2 to 5 run on the
  2026 public-use records with Census's person weights and 160 replicate
  weights. Sampling therefore drops out of every comparison until step 6
  changes the weights.
- **One swap per step.** A step replaces one set of Census values and holds
  everything else at Census's values, or at the previous step's.
- **Each step names the versions it ran.** The steps run PolicyEngine US
  through `policyengine.py`, which pins the model. Its main branch, read on
  8 November 2026, pins `policyengine-us` 2.2.1, `spm-calculator` 1.0.0
  and `policyengine-core` 3.33.3, and
  [policyengine.py#618](https://github.com/PolicyEngine/policyengine.py/issues/618)
  tracks the move to spm-calculator 1.1.0. This plan cites PolicyEngine US
  2.2.1 and spm-calculator 1.0.0, and says where PolicyEngine US's main
  branch differs. Each step records the versions of `policyengine.py`,
  PolicyEngine US, spm-calculator, policyengine-core and Microcosm that it
  ran, and checks this plan's claims about their code at those versions
  before it runs.
- **Census's values stay outside the model.** In PolicyEngine US 2.2.1, as
  on its main branch, `Simulation.set_input` refuses a dataset that
  stores an SPM measurement output: the thresholds and their housing
  portion, `spm_unit_capped_housing_subsidy`, `spm_unit_benefits`,
  `spm_unit_net_income` and the poverty flags, among others
  (`REJECTED_DATASET_INPUTS` in `policyengine_us/spm.py`). So the converted
  dataset carries none of Census's SPM outputs. Each step runs PolicyEngine
  US on the converted records, takes the components it swaps from that
  run, puts them in place of Census's in the file's resource identity, and
  compares the result with the file's `SPM_POVTHRESHOLD`. Thresholds stay
  Census's in steps 2 to 6, and the threshold track below swaps them
  separately.
- **Margins for the change, not only the level.** Each step reports the
  change in each estimate from the previous step with a replicate-weight
  margin of error: the same successive difference formula, applied to the
  difference computed under each replicate weight.
- **Unit-level comparisons first.** Before any poverty rate, each step sets
  PolicyEngine's value beside Census's for every record and reports the
  share that agree, the weighted totals and the largest disagreements.
- **Real runs through `policyengine.py`.** Every PolicyEngine value a step
  uses comes from a PolicyEngine US microsimulation run through
  `policyengine.py`, with the script, input checksums, results file and
  tests committed in this repository, as in step 1.
- **The dataset is Microcosm's.** Steps 2 to 5 build their dataset with
  Microcosm's raw ASEC stage, so that steps 3 and 5 can swap in Microcosm's
  own tax units and imputations.

## Before step 2: the public-use file as a PolicyEngine dataset

Microcosm already has a raw stage. Its
`tools/build_us_asec_pooled_source_base.py` builds the US unit frame from
raw CPS ASEC H5 files with `build_pooled_asec_unit_frame` and can write a
PolicyEngine H5 through `PolicyEngineUSEngine().write_dataset`. The tool's
docstring says that it "does not run donor imputations, fiscal calibration,
or release certification". `policyengine.py` reads PolicyEngine H5 files
into a `PolicyEngineUSDataset` (which takes a `name`, `description`,
`filepath` and `year`) and runs one with
`Simulation(dataset=..., tax_benefit_model_version=pe.us.model)`.

Four things need work before step 2 can use that path:

1. **One survey year at Census's weights.** The builder pools years and
   scales each to a population share. Step 2 needs the 2026 file alone, with
   `MARSUPWT / 100` and the replicate weights carried through unchanged.
2. **Census's units.** The builder constructs tax units itself through a
   `tax_unit_mode` argument, whose default is `"policyengine"`. Step 2 needs
   the file's own tax units (`TAX_ID`) and SPM units (`SPM_ID`). The first
   task checks whether an existing mode reproduces `TAX_ID` exactly, and
   adds one that reads `TAX_ID` if none does.
3. **An input census.** List every PolicyEngine US input the converter
   fills from the file, every input it leaves at its default, and the
   formulas that read the defaults, before any comparison runs. Some
   defaults change results, and some differ by version. In 2.2.1,
   `spm_unit_benefits` adds `unemployment_compensation`, an input with no
   formula, so a converter that leaves it empty gives every rule that
   reads it zero; on main it adds `total_unemployment_compensation`, which
   uses the reported amount where it is nonzero and
   `modeled_state_unemployment_compensation` elsewhere. Where `county_fips`
   is empty, `county` falls back to the first county in the household's
   state, and 84 other variables in 2.2.1 read `county` or `county_str`,
   among them county income taxes, county-grouped TANF rules and child
   care rates.
4. **Loading.** Confirm that `PolicyEngineUSDataset` loads the file the
   converter writes and that PolicyEngine US accepts it, which requires
   that the file store none of the refused SPM outputs. Record any
   provenance `policyengine.py` requires of a dataset it has not certified.

A gate closes this stage. The converted dataset must carry the file's
persons, tax units, SPM units and weights unchanged, and every PolicyEngine
US output must map back to the file's records one to one. With no component
swapped, the step calculation must reproduce step 1's results exactly.

## Step 2: taxes and credits

**Swap.** Replace Census's federal income tax before credits
(`SPM_FEDTAXBC`), EITC (`SPM_EITC`), refundable Child Tax Credit
(`SPM_ACTC`), state income tax (`SPM_STTAX`) and FICA (`SPM_FICA`) with
PolicyEngine US's values, computed on Census's tax units. Benefits,
expenses and thresholds stay Census's.

**PolicyEngine US counterparts.** In 2.2.1, `income_tax` equals
`income_tax_before_refundable_credits` minus the credits listed in
`gov.irs.credits.refundable`, which since 2022 names the EITC, the
refundable American Opportunity Credit, the refundable CTC, the recovery
rebate credit and the refundable payroll tax credit; main adds the claim
of right credit. `employee_payroll_tax` adds employee Social Security,
Medicare, Additional Medicare and state payroll taxes. `spm_unit_taxes`
adds payroll tax, self-employment tax, federal income tax (summed over the
unit's tax units), state income and use taxes, and a flat tax; main adds
local tax.

**Take-up and filing.** In 2.2.1, `eitc` multiplies the credit by
`takes_up_eitc` and by a filing condition that includes
`would_file_if_eligible_for_refundable_credit`, and both default to true.
Step 2 holds them there, so that the comparison isolates the rules, and
then runs a sub-step with Microcosm's EITC take-up, a random draw at rates
from 0.65 to 0.86 by number of children (`spec/take_up.yaml` in
`microcosm-build`, read at commit `3db6515`).

**The refundable CTC.** Step 1 applied the 2025 refundable CTC rule to the
file's own credits, earnings and dependents, and it gives every tax unit
with a refundable credit its `ACTC_CRD` within a dollar
([step 1](census-spm-reproduction.md)). So step 2's refundable CTC
comparison tests the inputs PolicyEngine US feeds the rule (qualifying
children, earnings and tax before credits) more than the rule itself.

**Line up the definitions first.** The data dictionary defines
`FEDTAX_AC = FEDTAX_BC - ACTC_CRD - EIT_CRED`, while `income_tax` subtracts
every listed refundable credit. It describes `SPM_FICA` as "Federal
Insurance Contributions Act and federal retirement contribution", while
PolicyEngine US's SPM taxes add self-employment tax and state payroll
taxes. Step 2 compares like with like: federal tax before credits with
`income_tax_before_refundable_credits`, each credit with its own variable,
and payroll taxes component by component.

**Report.** For each tax unit: agreement of each tax and credit with the
file's `FEDTAX_BC`, `EIT_CRED`, `ACTC_CRD`, `STATETAX_A` and `FICA`;
weighted totals; and the records with the largest gaps, with the inputs
behind them. Then Table 5's rows for the credits, federal income tax and
FICA, and the SPM rate, each beside step 1's.

## Step 3: tax units

**Swap.** Replace Census's tax units (`TAX_ID`) with Microcosm's
(`tax_unit_mode="policyengine"`), then rerun step 2's taxes and credits.

**Report.** The share of people whose tax unit changes, by relationship to
the unit head; filing status and dependent counts under each set of units;
the change in each tax and credit; and the change in the SPM rate from
step 2.

## Step 4: benefits

**Swap.** Replace Census's benefit values with PolicyEngine US's, one
program at a time and then together. In 2.2.1, `spm_unit_benefits` adds,
among other items, `snap`, `wic`, `free_school_meals`,
`reduced_price_school_meals`, `spm_unit_energy_subsidy`,
`spm_unit_capped_housing_subsidy`, `ssi` and the state supplements, `tanf`,
and Washington's `wa_sfa` and `wa_rca` cash programs; main adds others,
such as `ma_eaedc` and `ca_capi`. The Census values they replace are
`SPM_SNAPSUB`, `SPM_WICVAL`, `SPM_SCHLUNCH`, `SPM_ENGVAL`,
`SPM_CAPHOUSESUB`, `SSI_VAL` and `PAW_VAL`. The same sum adds items such as
Social Security and child support received, which step 4 leaves at the
file's values.

**Cash assistance.** `PAW_VAL` covers more than TANF. The data dictionary's
`PAW_TYP`, which the 2026 file carries, records whether a person's cash
assistance came from TANF or AFDC (1), another program (2) or both (3).
PolicyEngine US's `tanf` covers TANF alone, and its state cash programs
enter `spm_unit_benefits` beside it. So step 4 compares `tanf` with
`PAW_VAL` for type 1, the state cash programs with type 2, and their sum
with type 3, and reports the type 2 amounts that no PolicyEngine US
program matches.

**School meals.** The data dictionary calls `SPM_SCHLUNCH` the "SPM unit's
school lunch subsidy". In 2.2.1, `free_school_meals` and
`reduced_price_school_meals` value both meals: `school_meal_daily_subsidy`
adds the NSLP (lunch) and SBP (breakfast) rates for the unit's tier, and
main gives each meal its own tier. Step 4 compares the lunch part, computed
with the SBP rates set to zero, with `SPM_SCHLUNCH` first, and reports
breakfast on its own, as step 2 does for the tax definitions.

**Energy assistance.** `spm_unit_energy_subsidy` has no formula, so
PolicyEngine US has no energy assistance rule to swap in. Step 4 keeps
`SPM_ENGVAL` and reports energy assistance as not swapped.

**Housing.** PolicyEngine US builds the housing subsidy in three steps and
cites Census's SPM technical documentation for the last two.
`housing_assistance` multiplies HUD's housing assistance payment
(`hud_hap`) by `takes_up_housing_assistance_if_eligible`, for units with
`receives_housing_assistance` set and for renters whose HUD income level is
low or below. `spm_unit_allocated_housing_subsidy` sums that amount over
the household and divides the total among the household's SPM units by
their share of its members. `spm_unit_capped_housing_subsidy` then caps
each assisted unit's amount at the housing portion of its SPM threshold
less its allocated tenant payment, which PolicyEngine US builds from
`hud_ttp` the same way. That housing portion comes from spm-calculator's
bundled forecast, not from Census's threshold, so step 4 reports the
uncapped allocation beside `SPM_CAPHOUSESUB` as well as the capped amount.

**Housing geography.** Geography enters housing twice. HUD's fair market
rents and income limits come from each household's `county_fips`. A
household without one matches no row and gets zero for both, and with no
ZIP code to set another payment standard, its `hud_hap` is zero too
(`hud_fair_market_rent`, `lookup_income_limit` and `pha_payment_standard`
in 2.2.1). The cap's housing portion comes from the SPM provider, which
takes one geography selection for the whole run (`geography_kind` county,
metro or national, with one `geography_id`) and, under the county
selection, refuses a unit with no county; the cap asks only about assisted
units. The file gives no county (`GTCO` = 0) for more than half of its
households, and a synthetic `county_fips` would reach every rule that reads
it. So step 4 swaps housing only for households the file places in a
county, keeps `SPM_CAPHOUSESUB` for the rest, and reports how many of the
file's housing recipients (units with `SPM_CAPHOUSESUB` above zero) each
group holds.

**Take-up.** Rules give eligibility and amounts; take-up decides who
receives a benefit. PolicyEngine US reads take-up inputs such as
`takes_up_snap_if_eligible`, `takes_up_ssi_if_eligible`,
`takes_up_tanf_if_eligible`, `takes_up_wic_if_eligible` and
`takes_up_housing_assistance_if_eligible`, and each defaults to true.
Step 4 first sets each one to the file's reported receipt, so that it
isolates the rules, and then runs a sub-step with Microcosm's take-up
values. Microcosm's take-up specification (`spec/take_up.yaml` in
`microcosm-build`, read at commit `3db6515`) sets the five differently.
Housing take-up equals the receipt its `acs_rent` stage measures from
`SPM_CAPHOUSESUB`. SNAP take-up starts from reported receipt
(`SPM_SNAPSUB`), fills the rest at a national rate and recalibrates to
state caseloads. SSI keeps every reported recipient (`SSI_VAL`) and draws
the rest. WIC follows USDA participation rates by category. TANF take-up
is a random draw at 21.9 percent, ASPE's participation rate for 2022, with
no anchor to reported receipt, because Microcosm's base records do not
carry `PAW_VAL`. So the sub-step's TANF result reflects an administrative
rate rather than the file's reports, and step 4 reports it apart from the
other programs.

**Report.** For each program: eligibility and receipt agreement, amounts
among units that receive the benefit under both, weighted totals, the
Table 5 effect and the change in the SPM rate.

## Step 5: imputations the rules need

**Swap.** Add the inputs that benefit rules read but the public-use file
does not give, starting with rent for SNAP's shelter deduction.

**What the code does now.** In 2.2.1, as on main,
`snap_excess_shelter_expense_deduction` adds the SNAP utility allowance to
the counted share (`snap_expense_counted_share`) of the unit's
`housing_cost`. `housing_cost` adds `rent`, real estate taxes, homeowners
association fees, mortgage payments and homeowners insurance, and `rent`
spreads the unit's pre-subsidy rent, less its `housing_assistance` and
floored at zero, across members by their share of `pre_subsidy_rent`.
Microcosm's `acs_rent` stage fits a weighted quantile regression forest on
ACS 2022 rents, with household head status, age, sex, tenure, employment
and self-employment income, Social Security, pensions, state and household
size as predictors, and writes `pre_subsidy_rent`.

**Report.** The distribution of imputed rent by tenure; SNAP's shelter
deduction, benefit amounts and recipients before and after the imputation;
and the change in the SPM rate from step 4. The input census from the
converter stage lists the other defaults benefit formulas read; each one
that matters gets the same treatment.

## Step 6: calibration

**Swap.** Replace Census's weights with weights from
`microcosm-calibrate`, calibrated to Microcosm's US targets.

**Two parts.**

1. *The same records.* Calibrate the step 5 records and compare the SPM
   rate under Census's weights and under the calibrated ones. Replicate
   margins need one calibration per replicate weight, 160 in all; the step
   reports whether it ran them or a smaller set, and how many.
2. *The bridge to the release.* Compare the result with the SPM rate from
   Microcosm's certified US release. That release differs in more than
   weights, since it draws on other survey years and sources, so this part
   reports a bridge, not a single swap.

**Definitions in the bridge.** PolicyEngine US's own `spm_unit_net_income`
differs from the file's resource identity in definition as well as in
data. In 2.2.1 it adds `spm_unit_market_income`, `spm_unit_benefits` and
two broadband subsidies (`acp` and `ebb`), and subtracts `spm_unit_taxes`
and `spm_unit_spm_expenses`. The broadband subsidies have no line in the
identity, and neither do the child care subsidies that `spm_unit_benefits`
adds (Colorado's, Washington's and West Virginia's) or the premium tax
credit (`assigned_aca_ptc`) that it adds when a contributed reform's flag
is on. Cash transfers such as unemployment compensation sit in money income
(`SPM_TOTVAL`) in the identity and in `spm_unit_benefits` in PolicyEngine
US, whose market income leaves them out, so they change line but not
total. The bridge, and any step that compares with `spm_unit_net_income`
rather than the identity, lists these items.

**Report.** Weighted totals against each calibration target, the effective
sample size, the change in the SPM rate and the Table 4 rows, and the
bridge to the certified release.

## Thresholds, alongside the series

spm-calculator already replicates BLS's SPM thresholds from the
public Consumer Expenditure Survey Interview files, and records the
differences it measures ([CE replication](current-ce-replication.md)). It
also ships the thresholds that PolicyEngine US uses. PolicyEngine US
registers the package's threshold variables, `spm_unit_spm_threshold` among
them, and computes them through a `PolicyEngineSPMProvider` that
`policyengine_us/spm.py` builds from the package's bundled rolling forecast
(`rolling_forecast_2026_09_09.json`, in spm-calculator 1.0.0 as on its
main branch). PolicyEngine US 2.2.1 requires
`spm-calculator>=1.0.0,<=1.0.0.post1`, and PolicyEngine US's main branch
requires `>=1.1.0,<1.2`. A threshold step would replace each unit's
`SPM_POVTHRESHOLD` with PolicyEngine US's `spm_unit_spm_threshold` for the
same unit and year, and report the change in the SPM rate. That threshold
depends on each unit's tenure, composition and location. The provider
takes one geography selection for the whole run: county (its default),
metro or national, with one `geography_id`. It computes every unit's
threshold, and under the county selection it refuses a unit with no
county, while the public-use file gives no county for more than half of
its households. Using the file's metropolitan codes instead would take one
run per metropolitan area, or a synthetic `county_fips`, which HUD's
lookups and the county-based rules also read, so it would leak into steps
2 and 4. Step 1 also found that the file withholds some households'
metropolitan status. So the step starts by choosing among these
selections and listing the units whose location it cannot fix. It can run
at any point, since it touches no step above.

## Deliverables for each step

- A script that rebuilds every number from pinned inputs and writes a
  results file.
- A note with generated tables, like step 1's.
- Tests: identities, invariants (property tests), and the step's
  comparisons, with stated tolerances.
- An independent review before the note goes beyond PolicyEngine.
