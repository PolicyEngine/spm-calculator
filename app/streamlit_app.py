"""
SPM Threshold Calculator - Interactive Web Tool

A Streamlit app that walks users through calculating their SPM threshold
based on their household characteristics.

Run with: streamlit run app/streamlit_app.py
"""

import streamlit as st
import pandas as pd

# PolicyEngine Design System Colors
TEAL_500 = "#319795"
TEAL_600 = "#2C7A7B"
TEAL_700 = "#285E61"
GRAY_700 = "#344054"
GRAY_100 = "#F2F4F7"
BACKGROUND_SECONDARY = "#F5F9FF"
TEXT_PRIMARY = "#000000"
TEXT_SECONDARY = "#5A5A5A"

# PolicyEngine Logo
LOGO_URL = "https://raw.githubusercontent.com/PolicyEngine/policyengine-app/master/src/images/logos/policyengine/teal.png"

# Page config
st.set_page_config(
    page_title="SPM Threshold Calculator | PolicyEngine",
    page_icon="https://raw.githubusercontent.com/PolicyEngine/policyengine-app/master/src/images/logos/policyengine/favicon.png",
    layout="wide",
)

# PolicyEngine Design System CSS
st.markdown(
    f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}}

h1, h2, h3, h4, h5, h6 {{
    font-family: 'Inter', sans-serif;
    font-weight: 600;
    color: {GRAY_700};
}}

/* Primary button styling */
.stButton > button {{
    background-color: {TEAL_500};
    color: white;
    border: none;
    font-family: 'Inter', sans-serif;
    font-weight: 500;
}}

.stButton > button:hover {{
    background-color: {TEAL_600};
}}

/* Metric styling */
[data-testid="stMetricValue"] {{
    color: {TEAL_500};
    font-weight: 600;
}}

[data-testid="stMetricLabel"] {{
    color: {GRAY_700};
    font-weight: 500;
}}

/* Sidebar styling */
[data-testid="stSidebar"] {{
    background-color: {BACKGROUND_SECONDARY};
}}

[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {{
    color: {GRAY_700};
}}

/* Radio button styling */
.stRadio > label {{
    font-weight: 500;
}}

/* Selectbox styling */
.stSelectbox > label {{
    font-weight: 500;
}}

/* Number input styling */
.stNumberInput > label {{
    font-weight: 500;
}}

/* Slider styling */
.stSlider > label {{
    font-weight: 500;
}}

/* Table styling */
.dataframe {{
    font-family: 'Inter', sans-serif;
}}

/* Code block styling */
code {{
    background-color: {GRAY_100};
    padding: 2px 6px;
    border-radius: 4px;
}}

/* Link styling */
a {{
    color: {TEAL_500};
}}

a:hover {{
    color: {TEAL_700};
}}

/* Footer styling */
.footer {{
    text-align: center;
    padding: 20px;
    color: {TEXT_SECONDARY};
    font-size: 14px;
}}

/* Header container */
.header-container {{
    display: flex;
    align-items: center;
    gap: 16px;
    margin-bottom: 24px;
}}

.header-logo {{
    height: 48px;
}}

/* Card styling for results */
.result-card {{
    background-color: {BACKGROUND_SECONDARY};
    padding: 24px;
    border-radius: 8px;
    border-left: 4px solid {TEAL_500};
}}

/* Step headers */
.step-header {{
    color: {TEAL_600};
    font-weight: 600;
    margin-top: 24px;
}}
</style>
""",
    unsafe_allow_html=True,
)

# Header with logo
col_logo, col_title = st.columns([1, 11])
with col_logo:
    st.image(LOGO_URL, width=60)
with col_title:
    st.title("SPM Threshold Calculator")

st.markdown(
    """
Calculate your **Supplemental Poverty Measure (SPM) threshold** based on your
household characteristics. The SPM is used by the U.S. Census Bureau to measure
poverty more comprehensively than the official poverty measure.
"""
)

st.markdown(
    f"""
<div style="background-color: {BACKGROUND_SECONDARY}; padding: 16px; border-radius: 8px; margin: 16px 0;">
<strong>Formula:</strong> threshold = base_threshold × equivalence_scale × geographic_adjustment
</div>
""",
    unsafe_allow_html=True,
)

# Sidebar for inputs
st.sidebar.image(LOGO_URL, width=150)
st.sidebar.markdown("---")
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
        help="GEOADJ ranges from ~0.84 (low-cost) to ~1.27 (high-cost)",
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


# Base thresholds (BLS published)
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
    st.markdown(
        f"""
    <div style="background-color: {BACKGROUND_SECONDARY}; padding: 24px;
    border-radius: 8px; border-left: 4px solid {TEAL_500};">
        <p style="color: {TEXT_SECONDARY}; margin: 0; font-size: 14px;">
            SPM Threshold ({year})
        </p>
        <p style="color: {TEAL_500}; font-size: 48px; font-weight: 700;
        margin: 8px 0;">
            ${threshold:,.0f}
        </p>
        <p style="color: {GRAY_700}; margin: 0;">
            For a household with <strong>{num_adults}
            adult{'s' if num_adults != 1 else ''}</strong>
            and <strong>{num_children}
            child{'ren' if num_children != 1 else ''}</strong>
            who are <strong>{tenure.lower()}s</strong> in a
            <strong>{'above' if geoadj > 1 else 'below' if geoadj < 1
            else 'average'}-cost area</strong>.
        </p>
    </div>
    """,
        unsafe_allow_html=True,
    )

with col2:
    # Monthly equivalent
    monthly = threshold / 12
    st.markdown(
        f"""
    <div style="background-color: {GRAY_100}; padding: 24px;
    border-radius: 8px; text-align: center;">
        <p style="color: {TEXT_SECONDARY}; margin: 0; font-size: 14px;">
            Monthly Equivalent
        </p>
        <p style="color: {GRAY_700}; font-size: 32px; font-weight: 600;
        margin: 8px 0;">
            ${monthly:,.0f}
        </p>
    </div>
    """,
        unsafe_allow_html=True,
    )

st.markdown("<br>", unsafe_allow_html=True)

# Calculation breakdown
st.header("How It's Calculated")

st.markdown(
    f'<p class="step-header">Step 1: Base Threshold</p>', unsafe_allow_html=True
)
st.markdown(
    f"""
The base threshold is set by the BLS based on Consumer Expenditure Survey data.
For {year}, the base thresholds for a reference family (2 adults, 2 children)
are:

| Tenure Type | Base Threshold |
|-------------|---------------|
| Renter | ${BASE_THRESHOLDS[year]['renter']:,} |
| Owner with mortgage | ${BASE_THRESHOLDS[year]['owner_with_mortgage']:,} |
| Owner without mortgage | ${BASE_THRESHOLDS[year]['owner_without_mortgage']:,} |

**Your base threshold ({tenure}):** ${base:,}
"""
)

st.markdown(
    f'<p class="step-header">Step 2: Equivalence Scale</p>', unsafe_allow_html=True
)
raw_scale = spm_equivalence_scale(num_adults, num_children) * 2.1
adult_contrib = 1.0 + 0.5 * max(num_adults - 1, 0) if num_adults >= 1 else 0.0
child_contrib = 0.3 * num_children
st.markdown(
    f"""
The equivalence scale adjusts for family size using the three-parameter formula:
- First adult: **1.0**
- Additional adults: **+0.5 each**
- Children: **+0.3 each**

Your household:
- Adults: {num_adults} → 1.0 + {0.5 * max(num_adults - 1, 0):.1f} = \
**{adult_contrib:.1f}**
- Children: {num_children} × 0.3 = **{child_contrib:.1f}**
- **Raw scale: {raw_scale:.2f}**

Normalized to reference family (2A2C = 2.1):
- **Equivalence scale: {raw_scale:.2f} ÷ 2.1 = {equiv_scale:.3f}**
"""
)

st.markdown(
    '<p class="step-header">Step 3: Geographic Adjustment (GEOADJ)</p>',
    unsafe_allow_html=True,
)
st.markdown(
    f"""
GEOADJ adjusts for local housing costs using the formula:

$$\\text{{GEOADJ}} = \\frac{{\\text{{local median rent}}}}{{\\text{{national \
median rent}}}} \\times 0.492 + 0.508$$

Where 0.492 is the housing share of the SPM threshold for renters.

- GEOADJ ranges from ~0.84 (West Virginia) to ~1.27 (Hawaii)
- National average: 1.00

**Your GEOADJ: {geoadj:.2f}**
"""
)

st.markdown(
    '<p class="step-header">Step 4: Final Calculation</p>', unsafe_allow_html=True
)
st.markdown(
    f"""
<div style="background-color: {GRAY_100}; padding: 16px; border-radius: 8px;
font-family: monospace;">
Threshold = Base × Equivalence Scale × GEOADJ<br>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;= ${base:,} × \
{equiv_scale:.3f} × {geoadj:.2f}<br>
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;= \
<strong>${threshold:,.0f}</strong>
</div>
""",
    unsafe_allow_html=True,
)

st.markdown("<br>", unsafe_allow_html=True)

# Comparison chart
st.header("Comparison")

# Create comparison data
comparison_data = []
for t_name, t_key in tenure_map.items():
    for g_name, g_val in [
        ("Low-cost", 0.84),
        ("Average", 1.00),
        ("High-cost", 1.20),
    ]:
        t_base = BASE_THRESHOLDS[year][t_key]
        t_threshold = t_base * equiv_scale * g_val
        comparison_data.append(
            {
                "Tenure": t_name,
                "Location": g_name,
                "Threshold": t_threshold,
            }
        )

comparison_df = pd.DataFrame(comparison_data)

# Pivot for display
pivot_df = comparison_df.pivot(
    index="Tenure", columns="Location", values="Threshold"
)
pivot_df = pivot_df[["Low-cost", "Average", "High-cost"]]

st.markdown(
    f"""
Thresholds for different scenarios with {num_adults}
adult{'s' if num_adults != 1 else ''} and {num_children}
child{'ren' if num_children != 1 else ''}:
"""
)

# Format as currency
st.dataframe(
    pivot_df.style.format("${:,.0f}"),
    use_container_width=True,
)

st.markdown("<br>", unsafe_allow_html=True)

# Resources
st.header("Resources")
st.markdown(
    """
- [BLS SPM Thresholds](https://www.bls.gov/pir/spm/spm_thresholds_2024.htm) - \
Official threshold values
- [Census SPM Methodology]\
(https://www.census.gov/topics/income-poverty/supplemental-poverty-measure.html\
) - How SPM is calculated
- [spm-calculator on GitHub](https://github.com/PolicyEngine/spm-calculator) - \
Source code for this tool
"""
)

# Footer
st.markdown(
    f"""
<div class="footer">
    <hr style="border: none; border-top: 1px solid {GRAY_100}; margin: 24px 0;">
    <img src="{LOGO_URL}" height="32" style="margin-bottom: 8px;">
    <p>Built by <a href="https://policyengine.org">PolicyEngine</a> using the
    spm-calculator package.</p>
</div>
""",
    unsafe_allow_html=True,
)
