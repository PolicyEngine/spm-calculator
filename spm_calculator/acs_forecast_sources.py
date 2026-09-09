"""Offline, hash-pinned ACS source loading for the rolling research model."""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import textwrap
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

BUNDLE_SHA256 = (
    "39bd7832a0fad56ad0206c270e6106c384339d79fd569de25743f3f5adb51ba4"
)
CPI_RECEIPT_SHA256 = (
    "482678b4dc2070b434ff44b2d09417992b63546dea0ac3a30ec300244e14415e"
)
COMPONENTS = {
    "RNTP": "rent",
    "ELEP": "electricity",
    "GASP": "gas",
    "FULP": "fuel",
    "WATP": "water",
}
RAW_COLUMNS = {
    "SERIALNO",
    "STATE",
    "ST",
    "PUMA",
    "PUMA10",
    "PUMA20",
    "TYPEHUGQ",
    "NP",
    "TEN",
    "BDSP",
    "KIT",
    "PLM",
    "GRNTP",
    "ADJHSG",
    "WGTP",
    *COMPONENTS,
}


def sha256_file(path: Path) -> str:
    """Hash source bytes without reading an entire national archive into RAM."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_file(path: Path, expected_sha256: str) -> None:
    """Fail on missing or altered inputs, rather than falling back or fetching."""
    if sha256_file(path) != expected_sha256:
        raise ValueError(f"Source SHA256 mismatch: {Path(path).name}")


def load_source_bundle() -> dict:
    """Load committed compact inputs with an explicit content pin."""
    path = Path(__file__).parent / "data/current/acs_forecast_inputs.json"
    verify_file(path, BUNDLE_SHA256)
    return json.loads(path.read_text())


def load_historical_source_bundle() -> dict:
    """Read the2021product inputs with their complete content fingerprint."""
    from spm_calculator.release import canonical_bytes

    path = Path(__file__).parent / "data/current/acs_2021_source_inputs.json"
    bundle = json.loads(path.read_text())
    digest = hashlib.sha256(
        canonical_bytes(
            {
                key: value
                for key, value in bundle.items()
                if key != "content_sha256"
            }
        )
    ).hexdigest()
    if bundle.get("content_sha256") != digest:
        raise ValueError("Historical ACS source bundle hash mismatch")
    return bundle


def apply_puma_update(
    original: pd.DataFrame, update: pd.DataFrame
) -> pd.DataFrame:
    """Apply Census's SERIALNO join; PR-only update records never enter US data."""
    if (
        original.SERIALNO.duplicated().any()
        or update.SERIALNO.duplicated().any()
    ):
        raise ValueError("Duplicate SERIALNO in original or PUMA update")
    result = original.merge(
        update[["SERIALNO", "puma", "wgtp"]],
        on="SERIALNO",
        how="left",
        validate="one_to_one",
    )
    if result[["puma", "wgtp"]].isna().any().any():
        raise ValueError(
            "Missing PUMA/weight update for original housing record"
        )
    result["PUMA"] = result.pop("puma").astype(str).str.zfill(5)
    result["WGTP"] = result.pop("wgtp")
    result["STATE"] = result["ST"].astype(str).str.zfill(2)
    return result


def _universe(raw: pd.DataFrame) -> pd.Series:
    return (
        (raw.TYPEHUGQ == 1)
        & (raw.NP > 0)
        & (raw.TEN == 3)
        & (raw.BDSP == 2)
        & (raw.KIT == 1)
        & (raw.PLM == 1)
    )


def normalize_housing(
    raw: pd.DataFrame, vintage: int, topcodes: dict
) -> pd.DataFrame:
    """Select eligible units and apply the product housing-dollar factor once.

    Gross-rent censoring bounds are deliberately conservative: if any utility
    is topcoded, true gross rent is at least known cash rent; if cash rent is
    topcoded, at least its state threshold. Annual utility thresholds are
    compared to annual source amounts, not divided by twelve for flagging.
    """
    required = RAW_COLUMNS - {"ST", "PUMA10", "PUMA20"}
    if not required <= set(raw):
        raise ValueError(
            f"Missing housing fields: {sorted(required - set(raw))}"
        )
    data = raw.loc[_universe(raw) & (raw.GRNTP > 0) & (raw.WGTP > 0)].copy()
    if data.empty:
        return pd.DataFrame()
    if not data.SERIALNO.str.match(r"^\d{4}HU\d+$").all():
        raise ValueError("Unexpected housing SERIALNO survey-year format")
    years = data.SERIALNO.str[:4].astype(int)
    if not years.between(vintage - 4, vintage).all():
        raise ValueError("Cohort outside product window")
    # Census utility blanks mean included in rent/another bill, no charge or
    # not used. They are not missing gross rents and cannot be topcoded costs.
    for column in ("ELEP", "GASP", "FULP", "WATP"):
        data[column] = data[column].fillna(0.0)
    for column in ["GRNTP", "WGTP", "ADJHSG", *COMPONENTS]:
        if not np.isfinite(data[column]).all() or (data[column] < 0).any():
            raise ValueError(f"Invalid eligible housing {column}")
    if (data.ADJHSG <= 0).any():
        raise ValueError("ADJHSG must be positive")
    state = data.STATE.astype(str).str.zfill(2)
    puma = data.PUMA.astype(str).str.zfill(5)
    if (
        not state.str.fullmatch(r"\d{2}").all()
        or not puma.str.fullmatch(r"\d{5}").all()
    ):
        raise ValueError("Malformed STATE/PUMA")
    if (state.astype(int) >= 60).any():
        raise ValueError("National archive contains non-US state/territory")
    normalized = pd.DataFrame(
        {
            "record_id": data.SERIALNO.to_numpy(),
            "source_vintage": vintage,
            "cohort_year": years.to_numpy(),
            "source_year": years.to_numpy(),
            "puma_geoid": (state + puma).to_numpy(),
            "rent": (data.GRNTP * data.ADJHSG / 1e6).to_numpy(),
            "weight": data.WGTP.to_numpy(float),
            "raw_gross_rent": data.GRNTP.to_numpy(float),
            "adjhsg": data.ADJHSG.to_numpy(float),
            "projected": False,
        }
    )
    keys = years.astype(str) + ":" + state
    cash_threshold = None
    for variable, component in COMPONENTS.items():
        thresholds = {}
        for year, state_code in set(zip(years, state)):
            try:
                threshold = topcodes[str(year)][state_code][variable][
                    "threshold"
                ]
            except KeyError as error:
                raise ValueError(
                    f"Missing topcode source for {year}/{state_code}/{variable}"
                ) from error
            if threshold is not None and (
                not np.isfinite(threshold) or threshold <= 0
            ):
                raise ValueError("Invalid component topcode threshold")
            thresholds[f"{year}:{state_code}"] = (
                threshold if threshold is not None else np.inf
            )
        limits = keys.map(thresholds).to_numpy(float)
        normalized[f"top_{component}"] = (
            data[variable].to_numpy(float) >= limits
        )
        if variable == "RNTP":
            cash_threshold = limits
    flags = normalized[[f"top_{c}" for c in COMPONENTS.values()]].any(axis=1)
    cash_lower = np.where(
        normalized.top_rent, cash_threshold, data.RNTP.to_numpy(float)
    )
    adjusted_cash_lower = cash_lower * data.ADJHSG.to_numpy(float) / 1e6
    normalized["rent_lower_bound"] = np.where(
        flags,
        np.minimum(normalized.rent, adjusted_cash_lower),
        normalized.rent,
    )
    return normalized


def normalization_logic_sha256(vintage: int) -> str:
    """Fingerprint the normalization steps used by this product vintage."""
    functions = (_universe, normalize_housing, apply_puma_update)
    if vintage == 2021:
        functions += (_historical_housing, _restore_historical_record_ids)
    logic = "".join(
        ast.dump(ast.parse(textwrap.dedent(inspect.getsource(function))))
        for function in functions
    ) + json.dumps(COMPONENTS, sort_keys=True)
    return hashlib.sha256(logic.encode()).hexdigest()


def _pinned_normalized(cache_dir, vintage, bundle, source_hashes):
    """Reuse retained normalized bytes only when every scientific input agrees.

    Function AST identity ignores formatting while detecting normalization
    changes. Source archives are verified by the caller before this shortcut.
    """
    manifest = (
        Path(__file__).parent / "data/current/acs_normalized_products.json"
    )
    products = json.loads(manifest.read_text())
    product = products.get(str(vintage))
    if product is None:
        return None
    inputs = {
        "normalization_logic_sha256": normalization_logic_sha256(vintage),
        "source_sha256": source_hashes,
        "topcodes_sha256": hashlib.sha256(
            json.dumps(bundle["topcodes"], sort_keys=True).encode()
        ).hexdigest(),
        "valid_pumas_sha256": hashlib.sha256(
            json.dumps(
                sorted({r["puma_geoid"] for r in bundle["area_allocations"]})
            ).encode()
        ).hexdigest(),
    }
    if any(product[k] != value for k, value in inputs.items()):
        return None
    path = cache_dir / product["cache_path"]
    if not path.exists():
        return None
    verify_file(path, product["sha256"])
    with np.load(path, allow_pickle=False) as archive:
        return pd.DataFrame({key: archive[key] for key in product["columns"]})


def _historical_housing(raw):
    """Adapt the documented 2017–21 field/ID representation without changing IDs."""
    raw = raw.rename(columns={"ST": "STATE"}) if "STATE" not in raw else raw
    if "TYPEHUGQ" not in raw and "TYPE" in raw:
        raw = raw.rename(columns={"TYPE": "TYPEHUGQ"})
    raw = raw.copy()
    numeric = raw.SERIALNO.str.fullmatch(r"2017\d{9}")
    raw.loc[numeric, "SERIALNO"] = (
        "2017HU" + raw.loc[numeric, "SERIALNO"].str[4:]
    )
    return raw


def _restore_historical_record_ids(data):
    """Restore original numeric 2017 IDs after the common housing normalizer."""
    numeric = data.record_id.str.startswith("2017HU")
    data.loc[numeric, "record_id"] = (
        "2017" + data.loc[numeric, "record_id"].str[6:]
    )
    return data


def load_pums_records(
    cache_dir: Path,
    vintage: int,
    bundle: dict,
    *,
    use_normalized_cache: bool = True,
) -> pd.DataFrame:
    """Load one complete product, optionally reusing a verified normalized cache."""
    cache_dir = Path(cache_dir)
    paths = [f"{vintage}/csv_hus.zip"]
    if vintage == 2022:
        paths.append("2022/csv_h_update_puma.zip")
    sources = {s["cache_path"]: s for s in bundle["sources"]}
    for name in paths:
        verify_file(cache_dir / name, sources[name]["sha256"])
    if use_normalized_cache:
        retained = _pinned_normalized(
            cache_dir,
            vintage,
            bundle,
            [sources[name]["sha256"] for name in paths],
        )
        if retained is not None:
            return retained
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "sources": [sources[name]["sha256"] for name in paths],
                "parser": sha256_file(Path(__file__)),
                # Callers may supply a research bundle instead of the pin.
                # Every input affecting normalization or its validation must
                # participate in cache identity, including topcode edits.
                "topcodes": bundle["topcodes"],
                "valid_pumas": sorted(
                    {r["puma_geoid"] for r in bundle["area_allocations"]}
                ),
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    cached = cache_dir / "normalized" / f"{vintage}-{fingerprint}.npz"
    receipt = cached.with_suffix(".json")
    if use_normalized_cache and cached.exists() and receipt.exists():
        details = json.loads(receipt.read_text())
        verify_file(cached, details["sha256"])
        with np.load(cached, allow_pickle=False) as archive:
            return pd.DataFrame(
                {key: archive[key] for key in details["columns"]}
            )
    chunks = []
    with zipfile.ZipFile(cache_dir / paths[0]) as archive:
        members = sorted(
            name for name in archive.namelist() if name.endswith(".csv")
        )
        if members != [f"psam_hus{letter}.csv" for letter in "abcd"]:
            raise ValueError("Unexpected national housing archive members")
        for member in members:
            with archive.open(member) as stream:
                for chunk in pd.read_csv(
                    stream,
                    usecols=lambda c: c in RAW_COLUMNS or c == "TYPE",
                    dtype={
                        "SERIALNO": str,
                        "STATE": str,
                        "ST": str,
                        "PUMA": str,
                        "PUMA10": str,
                        "PUMA20": str,
                    },
                    chunksize=250_000,
                ):
                    if vintage == 2021:
                        chunk = _historical_housing(chunk)
                    chunk = chunk.loc[_universe(chunk)].copy()
                    if not chunk.empty:
                        chunks.append(chunk)
    raw = pd.concat(chunks, ignore_index=True)
    if vintage == 2022:
        selected = set(raw.SERIALNO)
        updates = []
        with zipfile.ZipFile(cache_dir / paths[1]) as archive:
            with archive.open("psam_h_update_puma.csv") as stream:
                for chunk in pd.read_csv(
                    stream,
                    usecols=["SERIALNO", "puma", "wgtp"],
                    dtype={"SERIALNO": str, "puma": str},
                    chunksize=250_000,
                ):
                    updates.append(chunk.loc[chunk.SERIALNO.isin(selected)])
        raw = apply_puma_update(raw, pd.concat(updates, ignore_index=True))
    data = normalize_housing(raw, vintage, bundle["topcodes"])
    if vintage == 2021:
        data = _restore_historical_record_ids(data)
    if data.record_id.duplicated().any() or set(data.cohort_year) != set(
        range(vintage - 4, vintage + 1)
    ):
        raise ValueError("Invalid source cohort or original-record coverage")
    valid_pumas = {r["puma_geoid"] for r in bundle["area_allocations"]}
    if set(data.puma_geoid) - valid_pumas:
        raise ValueError("Source contains PUMAs absent from pinned geography")
    if use_normalized_cache:
        cached.parent.mkdir(parents=True, exist_ok=True)
        arrays = {}
        for column in data:
            values = data[column].to_numpy()
            # Pandas 3 StringDtype also exports an object array. Persist only
            # numeric/bool/fixed-width strings; loading never enables pickle.
            arrays[column] = (
                values.astype(str) if values.dtype.hasobject else values
            )
        np.savez_compressed(cached, **arrays)
        receipt.write_text(
            json.dumps(
                {
                    "fingerprint": fingerprint,
                    "sha256": sha256_file(cached),
                    "columns": list(data),
                },
                sort_keys=True,
            )
            + "\n"
        )
    return data
