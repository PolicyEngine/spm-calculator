"""
Generate pre-computed GEOADJ data for the static React app.

This script generates JSON files containing GEOADJ values for all supported
geographies, enabling a fully static web app without server-side computation.
"""

import json
from pathlib import Path

# Base thresholds by year and tenure (from BLS)
BASE_THRESHOLDS = {
    "2024": {
        "renter": 39430,
        "owner_with_mortgage": 39068,
        "owner_without_mortgage": 32586,
    },
    "2023": {
        "renter": 36606,
        "owner_with_mortgage": 36192,
        "owner_without_mortgage": 30347,
    },
    "2022": {
        "renter": 33402,
        "owner_with_mortgage": 32949,
        "owner_without_mortgage": 27679,
    },
}

# Sample GEOADJ values by state (can be expanded with ACS data)
# These are illustrative - actual values should come from ACS median rents
STATE_GEOADJ = {
    "AL": 0.87,
    "AK": 1.15,
    "AZ": 0.98,
    "AR": 0.85,
    "CA": 1.22,
    "CO": 1.08,
    "CT": 1.12,
    "DE": 1.02,
    "DC": 1.25,
    "FL": 1.05,
    "GA": 0.96,
    "HI": 1.27,
    "ID": 0.93,
    "IL": 0.98,
    "IN": 0.88,
    "IA": 0.86,
    "KS": 0.87,
    "KY": 0.85,
    "LA": 0.88,
    "ME": 0.96,
    "MD": 1.12,
    "MA": 1.18,
    "MI": 0.90,
    "MN": 0.96,
    "MS": 0.84,
    "MO": 0.88,
    "MT": 0.92,
    "NE": 0.88,
    "NV": 1.02,
    "NH": 1.08,
    "NJ": 1.16,
    "NM": 0.90,
    "NY": 1.15,
    "NC": 0.94,
    "ND": 0.88,
    "OH": 0.88,
    "OK": 0.85,
    "OR": 1.06,
    "PA": 0.95,
    "RI": 1.08,
    "SC": 0.92,
    "SD": 0.86,
    "TN": 0.92,
    "TX": 0.96,
    "UT": 1.00,
    "VT": 1.02,
    "VA": 1.08,
    "WA": 1.12,
    "WV": 0.84,
    "WI": 0.90,
    "WY": 0.88,
}

STATE_NAMES = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "DC": "District of Columbia",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
}

# Location cost level presets
COST_LEVELS = {
    "national_average": {"geoadj": 1.00, "label": "National average"},
    "low_cost": {"geoadj": 0.84, "label": "Low-cost area"},
    "below_average": {"geoadj": 0.92, "label": "Below average"},
    "above_average": {"geoadj": 1.10, "label": "Above average"},
    "high_cost": {"geoadj": 1.20, "label": "High-cost area"},
    "very_high_cost": {"geoadj": 1.27, "label": "Very high-cost area"},
}


def generate_data():
    """Generate all pre-computed data for the React app."""
    output_dir = Path(__file__).parent.parent / "web" / "public" / "data"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate base thresholds
    with open(output_dir / "base_thresholds.json", "w") as f:
        json.dump(BASE_THRESHOLDS, f, indent=2)

    # Generate state GEOADJ values
    states_data = {
        code: {"name": STATE_NAMES[code], "geoadj": geoadj}
        for code, geoadj in STATE_GEOADJ.items()
    }
    with open(output_dir / "state_geoadj.json", "w") as f:
        json.dump(states_data, f, indent=2)

    # Generate cost level presets
    with open(output_dir / "cost_levels.json", "w") as f:
        json.dump(COST_LEVELS, f, indent=2)

    # Generate combined config for easy loading
    config = {
        "baseThresholds": BASE_THRESHOLDS,
        "states": states_data,
        "costLevels": COST_LEVELS,
        "methodology": {
            "equivalenceScale": {
                "firstAdult": 1.0,
                "additionalAdults": 0.5,
                "children": 0.3,
                "referenceFamily": 2.1,
            },
            "geoadjFormula": {
                "housingShare": 0.492,
                "nonHousingShare": 0.508,
            },
        },
    }
    with open(output_dir / "spm_config.json", "w") as f:
        json.dump(config, f, indent=2)

    print(f"Generated data files in {output_dir}")
    return config


if __name__ == "__main__":
    generate_data()
