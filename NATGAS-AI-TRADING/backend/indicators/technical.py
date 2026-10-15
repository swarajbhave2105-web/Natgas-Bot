"""Deterministic technical indicators.

AI agents will consume these calculations; they will not replace them.
"""

import pandas as pd


def add_basic_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["sma_20"] = out["close"].rolling(20).mean()
    out["sma_50"] = out["close"].rolling(50).mean()
    out["ema_20"] = out["close"].ewm(span=20, adjust=False).mean()

    delta = out["close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    # A one-way window has zero average losses. It is valid momentum data,
    # not missing data: RSI should resolve to 100 (and 50 for a flat window).
    rs = gain / loss.replace(0, pd.NA)
    out["rsi_14"] = 100 - (100 / (1 + rs))
    out.loc[(loss == 0) & (gain > 0), "rsi_14"] = 100.0
    out.loc[(loss == 0) & (gain == 0), "rsi_14"] = 50.0
    return out

def add_quant_trading_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add deterministic indicators inspired by je-suis-tm/quant-trading.

    This is an original NATGAS-specific implementation of the ideas in that
    Apache-2.0 repository; it does not import its scripts or assume its
    frictionless backtest model.
    """
    out = df.copy()
    required = {"open", "high", "low", "close"}
    missing = required.difference(out.columns)
    if missing:
        raise ValueError(f"Missing OHLC columns: {sorted(missing)}")

    close = out["close"]
    high = out["high"]
    low = out["low"]
    open_ = out["open"]

    # MACD-style momentum.
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    out["macd"] = ema12 - ema26
    out["macd_signal"] = out["macd"].ewm(span=9, adjust=False).mean()
    out["macd_hist"] = out["macd"] - out["macd_signal"]

    # Bollinger Bands / bandwidth.
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    out["bb_mid"] = bb_mid
    out["bb_upper"] = bb_mid + 2 * bb_std
    out["bb_lower"] = bb_mid - 2 * bb_std
    out["bb_width"] = (out["bb_upper"] - out["bb_lower"]) / bb_mid.replace(0, pd.NA)

    # Awesome Oscillator: 5/34 SMA of median price.
    median = (high + low) / 2
    out["awesome_oscillator"] = median.rolling(5).mean() - median.rolling(34).mean()

    # Heikin-Ashi transformation.
    ha_close = (open_ + high + low + close) / 4
    ha_open = pd.Series(index=out.index, dtype="float64")
    if len(out):
        ha_open.iloc[0] = (open_.iloc[0] + close.iloc[0]) / 2
        for i in range(1, len(out)):
            ha_open.iloc[i] = (ha_open.iloc[i - 1] + ha_close.iloc[i - 1]) / 2
    out["ha_open"] = ha_open
    out["ha_close"] = ha_close
    out["ha_bullish"] = out["ha_close"] > out["ha_open"]

    # Shooting-star geometry. This is a feature, not an automatic trade.
    body = (close - open_).abs()
    upper_wick = high - pd.concat([open_, close], axis=1).max(axis=1)
    lower_wick = pd.concat([open_, close], axis=1).min(axis=1) - low
    out["shooting_star"] = (
        (body > 0)
        & (upper_wick >= body * 2)
        & (lower_wick <= body)
        & (close < open_)
    )

    # Parabolic SAR using the standard recursive formulation.
    out["psar"] = _parabolic_sar(high, low)

    # Five-day Dual-Thrust-style reference range. The source repository uses
    # intraday execution; here we only expose the deterministic reference
    # levels so the live NATGAS pipeline can decide whether they are relevant.
    prev_high = high.shift(1)
    prev_low = low.shift(1)
    prev_close = close.shift(1)
    prev_open = open_.shift(1)
    rolling_high = high.shift(1).rolling(5).max()
    rolling_low = low.shift(1).rolling(5).min()
    range_ = pd.concat(
        [
            rolling_high - prev_low,
            prev_close.rolling(5).max() - rolling_low,
            (rolling_high - rolling_low),
        ],
        axis=1,
    ).max(axis=1)
    out["dual_thrust_upper"] = prev_open + 0.5 * range_
    out["dual_thrust_lower"] = prev_open - 0.5 * range_

    return out


def _parabolic_sar(
    high: pd.Series,
    low: pd.Series,
    step: float = 0.02,
    maximum: float = 0.2,
) -> pd.Series:
    if len(high) == 0:
        return pd.Series(index=high.index, dtype="float64")

    sar = pd.Series(index=high.index, dtype="float64")
    rising = True
    extreme = float(high.iloc[0])
    sar.iloc[0] = float(low.iloc[0])
    acceleration = step

    for i in range(1, len(high)):
        previous = float(sar.iloc[i - 1])
        candidate = previous + acceleration * (extreme - previous)

        if rising:
            candidate = min(candidate, float(low.iloc[i - 1]))
            if i >= 2:
                candidate = min(candidate, float(low.iloc[i - 2]))
            if float(low.iloc[i]) < candidate:
                rising = False
                candidate = extreme
                extreme = float(low.iloc[i])
                acceleration = step
            elif float(high.iloc[i]) > extreme:
                extreme = float(high.iloc[i])
                acceleration = min(maximum, acceleration + step)
        else:
            candidate = max(candidate, float(high.iloc[i - 1]))
            if i >= 2:
                candidate = max(candidate, float(high.iloc[i - 2]))
            if float(high.iloc[i]) > candidate:
                rising = True
                candidate = extreme
                extreme = float(high.iloc[i])
                acceleration = step
            elif float(low.iloc[i]) < extreme:
                extreme = float(low.iloc[i])
                acceleration = min(maximum, acceleration + step)

        sar.iloc[i] = candidate

    return sar
