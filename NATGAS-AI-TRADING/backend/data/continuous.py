"""Continuous NATGAS contract construction for research backtests.

The input is contract-level MCX Bhav Copy data. The builder selects one
contract per trading date and applies additive back-adjustment at contract
rolls so expiry-price gaps are not treated as economic returns.
"""

import pandas as pd


def build_continuous_contract(
    frame: pd.DataFrame,
    *,
    roll_days_before_expiry: int = 3,
    back_adjust: bool = True,
) -> pd.DataFrame:
    required = {"timestamp", "expiry", "close"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"missing columns: {missing}")
    if roll_days_before_expiry < 0:
        raise ValueError("roll_days_before_expiry cannot be negative")

    data = frame.copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"], errors="coerce")
    data["expiry"] = pd.to_datetime(data["expiry"], errors="coerce")
    data = data.dropna(subset=["timestamp", "expiry", "close"]).copy()
    data = data.sort_values(["timestamp", "expiry"]).reset_index(drop=True)
    data["days_to_expiry"] = (
        data["expiry"].dt.normalize() - data["timestamp"].dt.normalize()
    ).dt.days

    eligible = data[data["days_to_expiry"] >= roll_days_before_expiry].copy()
    if eligible.empty:
        eligible = data.copy()
    eligible["expiry_rank"] = eligible.groupby("timestamp")["expiry"].rank(
        method="first", ascending=True
    )
    selected = eligible[eligible["expiry_rank"] == 1].copy()

    missing_dates = sorted(set(data["timestamp"]) - set(selected["timestamp"]))
    if missing_dates:
        fallback = data[data["timestamp"].isin(missing_dates)].copy()
        fallback["expiry_rank"] = fallback.groupby("timestamp")["expiry"].rank(
            method="first", ascending=True
        )
        selected = pd.concat(
            [selected, fallback[fallback["expiry_rank"] == 1]],
            ignore_index=True,
        )

    selected = (
        selected.sort_values("timestamp")
        .drop_duplicates(subset=["timestamp"], keep="first")
        .reset_index(drop=True)
    )

    selected["contract"] = selected["expiry"].dt.strftime("%Y-%m-%d")
    selected["back_adjustment"] = 0.0

    if not back_adjust or len(selected) < 2:
        selected["continuous_close"] = selected["close"]
        return selected

    # Back-adjust history at each contract switch. A positive new-vs-old
    # close gap means older prices are shifted upward by that gap so the
    # synthetic continuous series does not create a false return at the roll.
    roll_positions = [
        i for i in range(1, len(selected))
        if selected.loc[i, "contract"] != selected.loc[i - 1, "contract"]
    ]

    for i in roll_positions:
        gap = float(selected.loc[i, "close"]) - float(selected.loc[i - 1, "close"])
        selected.loc[: i - 1, "back_adjustment"] += gap

    selected["continuous_close"] = selected["close"] + selected["back_adjustment"]

    for column in ("open", "high", "low"):
        if column in selected.columns:
            selected[f"continuous_{column}"] = (
                selected[column] + selected["back_adjustment"]
            )

    return selected
