"""MCX Bhav Copy ingestion and normalization for NATGAS research."""

from io import BytesIO, StringIO
from pathlib import Path
import pandas as pd


NATGAS_NAMES = {"NATURALGAS", "NATGAS", "NATURAL GAS"}


def _read_source(source: str | Path | bytes) -> pd.DataFrame:
    if isinstance(source, bytes):
        raw = source
    else:
        path = str(source)
        if path.lower().endswith((".xls", ".xlsx")):
            with open(path, "rb") as handle:
                raw = handle.read()
        else:
            return pd.read_csv(path)

    head = raw[:512].lstrip().lower()
    if b"<html" in head or b"<table" in head:
        tables = pd.read_html(StringIO(raw.decode("utf-8", errors="replace")))
        if not tables:
            raise ValueError("MCX HTML file contains no table")
        return tables[0]
    return pd.read_excel(BytesIO(raw))


def load_mcx_bhavcopy(source: str | Path | bytes) -> pd.DataFrame:
    """Load an MCX Bhav Copy and keep Natural Gas futures rows."""
    frame = _read_source(source)

    frame.columns = [
        str(column).strip().lower().replace(" ", "_").replace("(", "").replace(")", "")
        for column in frame.columns
    ]

    commodity_col = next(
        (c for c in frame.columns if c in {"commodity", "symbol", "scrip"}),
        None,
    )
    if commodity_col is None:
        raise ValueError("MCX file has no recognizable commodity column")

    names = frame[commodity_col].astype(str).str.strip().str.upper()
    frame = frame[names.isin(NATGAS_NAMES)].copy()

    aliases = {
        "open": ["open"],
        "high": ["high"],
        "low": ["low"],
        "close": ["close"],
        "volume": ["volume_lots", "volume", "vol_lots"],
        "open_interest": ["oi_lots", "open_interest_lots", "oi", "open_interest"],
        "expiry": ["expiry_date", "expiry"],
        "date": ["date", "trade_date"],
    }

    for target, candidates in aliases.items():
        if target not in frame.columns:
            match = next((c for c in candidates if c in frame.columns), None)
            if match:
                frame[target] = frame[match]

    required = {"open", "high", "low", "close"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"MCX NATGAS file missing columns: {missing}")

    if "date" in frame.columns:
        frame["timestamp"] = pd.to_datetime(frame["date"], errors="coerce")

    for column in ["open", "high", "low", "close", "volume", "open_interest"]:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

    frame = frame.dropna(subset=["open", "high", "low", "close"])

    if "expiry" in frame.columns:
        frame["expiry"] = pd.to_datetime(frame["expiry"], errors="coerce")

    return frame.reset_index(drop=True)
