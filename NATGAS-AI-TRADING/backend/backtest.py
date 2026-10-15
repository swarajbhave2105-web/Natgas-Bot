"""Leakage-aware, rupee-aware trade-level backtest engine for NATGAS research."""

from dataclasses import dataclass
import pandas as pd

CONTRACT_SIZE_MMBTU = 1250
TICK_SIZE_RUPEES = 0.10
RUPEES_PER_POINT = CONTRACT_SIZE_MMBTU


@dataclass(frozen=True)
class Trade:
    entry_time: object
    exit_time: object
    direction: int
    entry_price: float
    exit_price: float
    gross_points: float
    net_points: float
    gross_pnl: float
    net_pnl: float


@dataclass(frozen=True)
class BacktestMetrics:
    trades: int
    wins: int
    losses: int
    win_rate: float
    total_return: float
    max_drawdown: float
    gross_points: float
    net_points: float
    gross_pnl: float
    net_pnl: float
    profit_factor: float
    average_trade_points: float
    average_trade_pnl: float


def run_sma_trade_backtest(
    df: pd.DataFrame,
    *,
    initial_capital: float = 100_000.0,
    cost_points_per_side: float = 0.0,
    contract_size_mmbtu: int = CONTRACT_SIZE_MMBTU,
) -> tuple[pd.DataFrame, BacktestMetrics, list[Trade]]:
    """Backtest SMA20/SMA50 with next-bar-open execution.

    Signals are calculated from completed bars and shifted one bar before
    execution. P&L is converted from price points to rupees using the MCX
    contract size.
    """
    required = {"timestamp", "open", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")
    if contract_size_mmbtu <= 0:
        raise ValueError("contract_size_mmbtu must be positive")

    data = df.copy().sort_values("timestamp").reset_index(drop=True)
    data["sma_20"] = data["close"].rolling(20).mean()
    data["sma_50"] = data["close"].rolling(50).mean()
    raw_signal = (data["sma_20"] > data["sma_50"]).astype(int)
    raw_signal[data["sma_20"] < data["sma_50"]] = -1
    data["signal"] = raw_signal
    data["target_position"] = data["signal"].shift(1).fillna(0)

    trades: list[Trade] = []
    position = 0
    entry_price = None
    entry_time = None
    equity = initial_capital
    equity_curve = []

    for _, row in data.iterrows():
        target = int(row["target_position"])

        if target != position and entry_price is not None:
            exit_price = float(row["open"])
            gross = (exit_price - entry_price) * position
            net = gross - (2 * cost_points_per_side)
            gross_pnl = gross * contract_size_mmbtu
            net_pnl = net * contract_size_mmbtu
            trades.append(Trade(
                entry_time, row["timestamp"], position,
                entry_price, exit_price, gross, net, gross_pnl, net_pnl,
            ))
            equity += net_pnl
            position = 0
            entry_price = None
            entry_time = None

        if target != position and target != 0:
            position = target
            entry_price = float(row["open"])
            entry_time = row["timestamp"]

        equity_curve.append(equity)

    if position and entry_price is not None and len(data):
        row = data.iloc[-1]
        exit_price = float(row["close"])
        gross = (exit_price - entry_price) * position
        net = gross - (2 * cost_points_per_side)
        gross_pnl = gross * contract_size_mmbtu
        net_pnl = net * contract_size_mmbtu
        trades.append(Trade(
            entry_time, row["timestamp"], position,
            entry_price, exit_price, gross, net, gross_pnl, net_pnl,
        ))
        equity += net_pnl
        equity_curve[-1] = equity

    data["equity"] = equity_curve
    peak = data["equity"].cummax()
    drawdown = data["equity"] / peak - 1

    wins = sum(t.net_pnl > 0 for t in trades)
    losses = sum(t.net_pnl < 0 for t in trades)
    gross_profit = sum(t.net_pnl for t in trades if t.net_pnl > 0)
    gross_loss = -sum(t.net_pnl for t in trades if t.net_pnl < 0)

    metrics = BacktestMetrics(
        trades=len(trades),
        wins=wins,
        losses=losses,
        win_rate=wins / (wins + losses) if wins + losses else 0.0,
        total_return=(equity / initial_capital) - 1,
        max_drawdown=float(drawdown.min()) if len(drawdown) else 0.0,
        gross_points=sum(t.gross_points for t in trades),
        net_points=sum(t.net_points for t in trades),
        gross_pnl=sum(t.gross_pnl for t in trades),
        net_pnl=sum(t.net_pnl for t in trades),
        profit_factor=(gross_profit / gross_loss) if gross_loss else float("inf"),
        average_trade_points=(sum(t.net_points for t in trades) / len(trades)) if trades else 0.0,
        average_trade_pnl=(sum(t.net_pnl for t in trades) / len(trades)) if trades else 0.0,
    )
    return data, metrics, trades
