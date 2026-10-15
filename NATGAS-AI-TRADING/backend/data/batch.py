"""Batch loading and normalization for MCX NATGAS Bhav Copy files."""

from pathlib import Path
import pandas as pd

from backend.data.providers.mcx_bhavcopy import load_mcx_bhavcopy


def load_mcx_natgas_history(sources: list[str | Path | bytes]) -> pd.DataFrame:
    """Load multiple Bhav Copy files into one de-duplicated NATGAS history."""
    frames = [load_mcx_bhavcopy(source) for source in sources]
    if not frames:
        return pd.DataFrame()

    data = pd.concat(frames, ignore_index=True)

    if "timestamp" in data.columns:
        data["timestamp"] = pd.to_datetime(data["timestamp"], errors="coerce")
    if "expiry" in data.columns:
        data["expiry"] = pd.to_datetime(data["expiry"], errors="coerce")

    # A monthly Bhav Copy download can overlap another download. Prefer the
    # latest occurrence of an identical contract/date record.
    keys = [column for column in ("timestamp", "symbol", "expiry", "instrument_name") if column in data.columns]
    if keys:
        data = data.drop_duplicates(subset=keys, keep="last")

    return data.sort_values(
        [column for column in ("timestamp", "expiry") if column in data.columns]
    ).reset_index(drop=True)
