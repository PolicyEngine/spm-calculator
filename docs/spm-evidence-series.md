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
- **Margins for the change, not only the level.** Each step reports the
  change in each estimate from the previous step with a replicate-weight
  margin of error: the same successive difference formula, applied to the
  difference computed under each replicate weight.
- **Unit-level comparisons first.** Before any poverty rate, each step sets
  PolicyEngine's value beside Census's for every record and reports the
  share that agree, the weighted totals and the largest disagreements.
- **Real runs through `policyengine.py`.** Every number comes from a
  PolicyEngine US microsimulation run through `policyengine.py`, with the
  script, input checksums, results file and tests committed in this
  repository, as in step 1.
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
   formulas that read the defaults, before any comparison runs.
4. **Loading.** Confirm that `PolicyEngineUSDataset` loads the file the
   converter writes, and record any provenance `policyengine.py` requires of
   a dataset it has not certified.

A gate closes this stage: with every SPM element set to Census's values,
the converted dataset must reproduce step 1's results exactly.

## Step 2: taxes and credits

**Swap.** Replace Census's federal income tax before credits
(`SPM_FEDTAXBC`), EITC (`SPM_EITC`), refundable Child Tax Credit
(`SPM_ACTC`), state income tax (`SPM_STTAX`) and FICA (`SPM_FICA`) with
PolicyEngine US's values, computed on Census's tax units. Benefits,
expenses and thresholds stay Census's.

**PolicyEngine US counterparts.** On `policyengine-us` main, read on 7
November 2026: `income_tax` equals `income_tax_before_refundable_credits`
minus the credits listed in `gov.irs.credits.refundable`, which since 2022
names the EITC, the refundable American Opportunity Credit, the refundable
CTC, the recovery rebate credit, the refundable payroll tax credit and the
claim of right credit. `employee_payroll_tax` adds employee Social
Security, Medicare, Additional Medicare and state payroll taxes.
`spm_unit_taxes` adds payroll tax, self-employment tax, federal income tax
(summed over the unit's tax units), state income and use taxes, local tax
and a flat tax.

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

**Swap.** Replace Census's benefit values with PolicyEngine US's
rule-computed ones, one program at a time and then together. On
`policyengine-us` main, `spm_unit_benefits` includes `snap`, `wic`,
`free_school_meals`, `reduced_price_school_meals`,
`spm_unit_energy_subsidy`, `spm_unit_capped_housing_subsidy`, `ssi` and the
state supplements, and `tanf`. The Census values they replace are
`SPM_SNAPSUB`, `SPM_WICVAL`, `SPM_SCHLUNCH`, `SPM_ENGVAL`,
`SPM_CAPHOUSESUB`, `SSI_VAL` and `PAW_VAL`.

**Take-up.** Rules give eligibility and amounts; take-up decides who
receives a benefit. PolicyEngine US reads take-up inputs such as
`takes_up_snap_if_eligible`, `takes_up_ssi_if_eligible`,
`takes_up_tanf_if_eligible`, `takes_up_wic_if_eligible` and
`takes_up_housing_assistance_if_eligible`. Step 4 first sets each one to
the file's reported receipt, so that it isolates the rules, and then runs a
sub-step with PolicyEngine's take-up assignment.

**Report.** For each program: eligibility and receipt agreement, amounts
among units that receive the benefit under both, weighted totals, the
Table 5 effect and the change in the SPM rate.

## Step 5: imputations the rules need

**Swap.** Add the inputs that benefit rules read but the public-use file
does not give, starting with rent for SNAP's shelter deduction.

**What the code does now.** On `policyengine-us` main,
`snap_excess_shelter_expense_deduction` reads the unit's `housing_cost` and
the SNAP utility allowance. `housing_cost` adds `rent`, real estate taxes,
homeowners association fees, mortgage payments and homeowners insurance,
and `rent` spreads the unit's pre-subsidy rent, less its housing
assistance, across members by their share of `pre_subsidy_rent`.
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

**Report.** Weighted totals against each calibration target, the effective
sample size, the change in the SPM rate and the Table 4 rows, and the
bridge to the certified release.

## Thresholds, alongside the series

spm-calculator already replicates BLS's SPM thresholds from the
public Consumer Expenditure Survey Interview files, and records the
differences it measures ([CE replication](current-ce-replication.md)). A
threshold step would replace each unit's `SPM_POVTHRESHOLD` with the
package's threshold for the same unit and year, and report the change in
the SPM rate. The package's thresholds depend on each unit's tenure,
composition and location, and step 1 found that the public-use file
withholds some households' metropolitan status, so the step starts by
listing the units whose location it cannot fix. It can run at any point,
since it touches no step above.

## Deliverables for each step

- A script that rebuilds every number from pinned inputs and writes a
  results file.
- A note with generated tables, like step 1's.
- Tests: identities, invariants (property tests), and the step's
  comparisons, with stated tolerances.
- An independent review before the note goes beyond PolicyEngine.
