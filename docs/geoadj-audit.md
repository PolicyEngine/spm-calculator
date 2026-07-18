# Geographic adjustment oracle audit

The custom-geography path computes `geoadj = rent_ratio x share + (1 - share)` from ACS median gross rents. This audit scores the package's actual formula against the Census SPM metro workbook's official per-metro, per-tenure adjustments — the first ground-truth test this code path has had.

Oracle: Census Bureau SPM Thresholds by Metro Area 2024. ACS: 2023 5-year summary file.

## Formula shape

Running the package formula on the workbook's own rent index reproduces the workbook adjustments to within 0.0017% — the linear share formula is exactly Census's construction.

## Rent definition

| Rent table | Tenure | End-to-end MAE | Median | p90 | Max |
|---|---|---:|---:|---:|---:|
| overall_median_rent_b25064 | renter | 1.60% | 1.26% | 3.33% | 6.91% |
| overall_median_rent_b25064 | owner_with_mortgage | 1.56% | 1.23% | 3.26% | 6.75% |
| overall_median_rent_b25064 | owner_without_mortgage | 1.16% | 0.91% | 2.45% | 4.87% |
| two_bedroom_rent_b25031 | renter | 0.44% | 0.30% | 0.98% | 2.99% |
| two_bedroom_rent_b25031 | owner_with_mortgage | 0.43% | 0.30% | 0.95% | 2.93% |
| two_bedroom_rent_b25031 | owner_without_mortgage | 0.32% | 0.22% | 0.71% | 2.22% |

- overall_median_rent_b25064: rent index vs workbook index MAE 3.79%, median 3.29%, p90 7.44%, max 18.50% (n=256).
- two_bedroom_rent_b25031: rent index vs workbook index MAE 1.08%, median 0.73%, p90 2.41%, max 6.39% (n=256).

The two-bedroom rent table (B25031) matches the workbook's rent concept roughly three times more closely than the overall median rent (B25064) the custom path uses today — consistent with Census's documented use of two-bedroom gross rents for SPM geographic adjustment. Switching the custom-geography rent source to B25031 and regenerating the bundled sub-metro data is the follow-up this audit motivates.

## Ten largest end-to-end errors (two-bedroom rents)

| Metro | Tenure | Formula | Oracle | Error |
|---|---|---:|---:|---:|
| Bend-Redmond, OR MSA | renter | 1.035 | 1.067 | -2.99% |
| New Haven-Milford, CT MSA | renter | 1.066 | 1.035 | +2.95% |
| Bend-Redmond, OR MSA | owner_with_mortgage | 1.035 | 1.066 | -2.93% |
| New Haven-Milford, CT MSA | owner_with_mortgage | 1.064 | 1.034 | +2.90% |
| Blacksburg-Christiansburg-Radford, VA MSA | renter | 0.895 | 0.918 | -2.42% |
| Clarksville, TN-KY MSA | renter | 0.903 | 0.925 | -2.39% |
| Blacksburg-Christiansburg-Radford, VA MSA | owner_with_mortgage | 0.898 | 0.919 | -2.37% |
| Clarksville, TN-KY MSA | owner_with_mortgage | 0.905 | 0.927 | -2.34% |
| Bend-Redmond, OR MSA | owner_without_mortgage | 1.026 | 1.049 | -2.22% |
| New Haven-Milford, CT MSA | owner_without_mortgage | 1.048 | 1.026 | +2.17% |
