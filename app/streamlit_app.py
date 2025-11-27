"""
SPM Threshold Calculator - Interactive Web Tool

A Streamlit app that walks users through calculating their SPM threshold
based on their household characteristics.

Run with: streamlit run app/streamlit_app.py
"""

import streamlit as st
import pandas as pd
import numpy as np

# Page config
st.set_page_config(
    page_title="SPM Threshold Calculator",
    page_icon="📊",
    layout="wide",
)

# Title and intro
st.title("📊 SPM Threshold Calculator")
st.markdown("""
Calculate your **Supplemental Poverty Measure (SPM) threshold** based on your
household characteristics. The SPM is used by the U.S. Census Bureau to measure
poverty more comprehensively than the official poverty measure.

The SPM threshold is calculated as:
```
threshold = base_threshold × equivalence_scale × geographic_adjustment
```
""")

# Sidebar for inputs
st.sidebar.header("Your Household")

# Year selection
year = st.sidebar.selectbox(
    "Year",
    options=[2024, 2023, 2022],
    index=0,
    help="The year for which to calculate the threshold",
)

# Family composition
st.sidebar.subheader("Family Composition")

num_adults = st.sidebar.number_input(
    "Number of adults (18+)",
    min_value=0,
    max_value=10,
    value=2,
    help="Number of people 18 years or older in your SPM unit",
)

num_children = st.sidebar.number_input(
    "Number of children (under 18)",
    min_value=0,
    max_value=15,
    value=2,
    help="Number of people under 18 in your SPM unit",
)

# Housing tenure
st.sidebar.subheader("Housing")

tenure = st.sidebar.radio(
    "Housing tenure",
    options=["Renter", "Owner with mortgage", "Owner without mortgage"],
    index=0,
    help="Your housing situation affects the threshold",
)

tenure_map = {
    "Renter": "renter",
    "Owner with mortgage": "owner_with_mortgage",
    "Owner without mortgage": "owner_without_mortgage",
}
tenure_key = tenure_map[tenure]

# Geographic adjustment
st.sidebar.subheader("Location")

use_custom_geoadj = st.sidebar.checkbox(
    "Use custom geographic adjustment",
    value=False,
    help="Check to enter a custom GEOADJ value",
)

if use_custom_geoadj:
    geoadj = st.sidebar.slider(
        "Geographic adjustment (GEOADJ)",
        min_value=0.70,
        max_value=1.50,
        value=1.00,
        step=0.01,
        help="GEOADJ ranges from ~0.84 (low-cost areas) to ~1.27 (high-cost areas)",
    )
else:
    location_type = st.sidebar.selectbox(
        "Location cost level",
        options=[
            "National average",
            "Low-cost area (e.g., West Virginia)",
            "Below average",
            "Above average",
            "High-cost area (e.g., San Francisco)",
            "Very high-cost (e.g., Hawaii)",
        ],
    )
    geoadj_map = {
        "National average": 1.00,
        "Low-cost area (e.g., West Virginia)": 0.84,
        "Below average": 0.92,
        "Above average": 1.10,
        "High-cost area (e.g., San Francisco)": 1.20,
        "Very high-cost (e.g., Hawaii)": 1.27,
    }
    geoadj = geoadj_map[location_type]


# Base thresholds (BLS published 2024)
BASE_THRESHOLDS = {
    2024: {
        "renter": 39430,
        "owner_with_mortgage": 39068,
        "owner_without_mortgage": 32586,
    },
    2023: {
        "renter": 36606,
        "owner_with_mortgage": 36192,
        "owner_without_mortgage": 30347,
    },
    2022: {
        "renter": 33402,
        "owner_with_mortgage": 32949,
        "owner_without_mortgage": 27679,
    },
}


def spm_equivalence_scale(adults: int, children: int) -> float:
    """Calculate SPM three-parameter equivalence scale."""
    if adults == 0 and children == 0:
        return 0.0

    # First adult = 1.0, additional adults = 0.5 each
    adult_scale = 1.0 + 0.5 * max(adults - 1, 0) if adults >= 1 else 0.0
    child_scale = 0.3 * children

    raw_scale = adult_scale + child_scale
    reference_scale = 2.1  # 2A2C

    return raw_scale / reference_scale


# Calculate components
base = BASE_THRESHOLDS[year][tenure_key]
equiv_scale = spm_equivalence_scale(num_adults, num_children)
threshold = base * equiv_scale * geoadj

# Display results
st.header("Your SPM Threshold")

col1, col2 = st.columns([2, 1])

with col1:
    st.metric(
        label=f"SPM Threshold ({year})",
        value=f"${threshold:,.0f}",
        help="Annual household income below this level would be considered in poverty under the SPM",
    )

    st.markdown(f"""
    For a household with **{num_adults} adult{'s' if num_adults != 1 else ''}**
    and **{num_children} child{'ren' if num_children != 1 else ''}**
    who are **{tenure.lower()}s** in a **{'above' if geoadj > 1 else 'below' if geoadj < 1 else 'average'}-cost area**.
    """)

with col2:
    # Monthly equivalent
    monthly = threshold / 12
    st.metric(
        label="Monthly Equivalent",
        value=f"${monthly:,.0f}",
    )

# Calculation breakdown
st.header("How It's Calculated")

st.markdown("### Step 1: Base Threshold")
st.markdown(f"""
The base threshold is set by the BLS based on Consumer Expenditure Survey data.
For {year}, the base thresholds for a reference family (2 adults, 2 children) are:

| Tenure Type | Base Threshold |
|-------------|---------------|
| Renter | ${BASE_THRESHOLDS[year]['renter']:,} |
| Owner with mortgage | ${BASE_THRESHOLDS[year]['owner_with_mortgage']:,} |
| Owner without mortgage | ${BASE_THRESHOLDS[year]['owner_without_mortgage']:,} |

**Your base threshold ({tenure}):** ${base:,}
""")

st.markdown("### Step 2: Equivalence Scale")
raw_scale = spm_equivalence_scale(num_adults, num_children) * 2.1
st.markdown(f"""
The equivalence scale adjusts for family size using the three-parameter formula:
- First adult: **1.0**
- Additional adults: **+0.5 each**
- Children: **+0.3 each**

Your household:
- Adults: {num_adults} → {1.0 if num_adults >= 1 else 0.0} + {0.5 * max(num_adults - 1, 0):.1f} = **{1.0 + 0.5 * max(num_adults - 1, 0) if num_adults >= 1 else 0.0:.1f}**
- Children: {num_children} × 0.3 = **{0.3 * num_children:.1f}**
- **Raw scale: {raw_scale:.2f}**

Normalized to reference family (2A2C = 2.1):
- **Equivalence scale: {raw_scale:.2f} ÷ 2.1 = {equiv_scale:.3f}**
""")

st.markdown("### Step 3: Geographic Adjustment (GEOADJ)")
st.markdown(f"""
GEOADJ adjusts for local housing costs using the formula:

$$\\text{{GEOADJ}} = \\frac{{\\text{{local median rent}}}}{{\\text{{national median rent}}}} \\times 0.492 + 0.508$$

Where 0.492 is the housing share of the SPM threshold for renters.

- GEOADJ ranges from ~0.84 (West Virginia) to ~1.27 (Hawaii)
- National average: 1.00

**Your GEOADJ: {geoadj:.2f}**
""")

st.markdown("### Step 4: Final Calculation")
st.markdown(f"""
```
Threshold = Base × Equivalence Scale × GEOADJ
         = ${base:,} × {equiv_scale:.3f} × {geoadj:.2f}
         = ${threshold:,.0f}
```
""")

# Comparison chart
st.header("Comparison")

# Create comparison data
comparison_data = []
for t_name, t_key in tenure_map.items():
    for g_name, g_val in [("Low-cost", 0.84), ("Average", 1.00), ("High-cost", 1.20)]:
        t_base = BASE_THRESHOLDS[year][t_key]
        t_threshold = t_base * equiv_scale * g_val
        comparison_data.append({
            "Tenure": t_name,
            "Location": g_name,
            "Threshold": t_threshold,
        })

comparison_df = pd.DataFrame(comparison_data)

# Pivot for display
pivot_df = comparison_df.pivot(index="Tenure", columns="Location", values="Threshold")
pivot_df = pivot_df[["Low-cost", "Average", "High-cost"]]

st.markdown(f"""
Thresholds for different scenarios with {num_adults} adult{'s' if num_adults != 1 else ''}
and {num_children} child{'ren' if num_children != 1 else ''}:
""")

# Format as currency
st.dataframe(
    pivot_df.style.format("${:,.0f}"),
    use_container_width=True,
)

# Resources
st.header("Resources")
st.markdown("""
- [BLS SPM Thresholds](https://www.bls.gov/pir/spm/spm_thresholds_2024.htm) - Official threshold values
- [Census SPM Methodology](https://www.census.gov/topics/income-poverty/supplemental-poverty-measure.html) - How SPM is calculated
- [spm-calculator on GitHub](https://github.com/PolicyEngine/spm-calculator) - Source code for this tool

---
*Built by [PolicyEngine](https://policyengine.org) using the spm-calculator package.*
""")
