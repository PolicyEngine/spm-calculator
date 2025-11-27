"""
Generate pre-computed GEOADJ data for the static React app.

This script generates JSON files containing GEOADJ values for all supported
geographies, enabling a fully static web app without server-side computation.
"""

import json
from pathlib import Path

# Historical BLS thresholds (2015-2024)
HISTORICAL_THRESHOLDS = {
    "2015": {
        "renter": 25155,
        "owner_with_mortgage": 24859,
        "owner_without_mortgage": 20639,
    },
    "2016": {
        "renter": 25558,
        "owner_with_mortgage": 25248,
        "owner_without_mortgage": 20943,
    },
    "2017": {
        "renter": 26213,
        "owner_with_mortgage": 25897,
        "owner_without_mortgage": 21527,
    },
    "2018": {
        "renter": 26905,
        "owner_with_mortgage": 26565,
        "owner_without_mortgage": 22095,
    },
    "2019": {
        "renter": 27515,
        "owner_with_mortgage": 27172,
        "owner_without_mortgage": 22600,
    },
    "2020": {
        "renter": 28881,
        "owner_with_mortgage": 28533,
        "owner_without_mortgage": 23948,
    },
    "2021": {
        "renter": 31453,
        "owner_with_mortgage": 31089,
        "owner_without_mortgage": 26022,
    },
    "2022": {
        "renter": 33402,
        "owner_with_mortgage": 32949,
        "owner_without_mortgage": 27679,
    },
    "2023": {
        "renter": 36606,
        "owner_with_mortgage": 36192,
        "owner_without_mortgage": 30347,
    },
    "2024": {
        "renter": 39430,
        "owner_with_mortgage": 39068,
        "owner_without_mortgage": 32586,
    },
}

# CPI projections for forecasting
CPI_PROJECTIONS = {
    2025: 0.025,  # 2.5%
    2026: 0.023,  # 2.3%
    2027: 0.022,  # 2.2%
    2028: 0.020,  # 2.0%
    2029: 0.020,
    2030: 0.020,
}

LATEST_PUBLISHED_YEAR = 2024


def forecast_thresholds(year: int) -> dict:
    """Forecast thresholds for a future year."""
    base = HISTORICAL_THRESHOLDS[str(LATEST_PUBLISHED_YEAR)]

    # Calculate cumulative inflation
    factor = 1.0
    for y in range(LATEST_PUBLISHED_YEAR + 1, year + 1):
        rate = CPI_PROJECTIONS.get(y, 0.020)
        factor *= (1 + rate)

    return {
        tenure: int(round(value * factor))
        for tenure, value in base.items()
    }


# Generate thresholds for all years including forecasts
def generate_all_thresholds():
    """Generate thresholds for historical and forecast years."""
    all_thresholds = dict(HISTORICAL_THRESHOLDS)

    # Add forecasted years
    for year in range(LATEST_PUBLISHED_YEAR + 1, 2031):
        all_thresholds[str(year)] = forecast_thresholds(year)

    return all_thresholds


# Sample GEOADJ values by state (can be expanded with ACS data)
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

    # Generate all thresholds (historical + forecast)
    all_thresholds = generate_all_thresholds()
    with open(output_dir / "base_thresholds.json", "w") as f:
        json.dump(all_thresholds, f, indent=2)

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
        "baseThresholds": all_thresholds,
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
        "forecast": {
            "latestPublishedYear": LATEST_PUBLISHED_YEAR,
            "cpiProjections": {str(k): v for k, v in CPI_PROJECTIONS.items()},
            "defaultInflation": 0.020,
        },
    }
    with open(output_dir / "spm_config.json", "w") as f:
        json.dump(config, f, indent=2)

    print(f"Generated data files in {output_dir}")
    print(f"Years available: {sorted(all_thresholds.keys())}")
    return config


if __name__ == "__main__":
    generate_data()
