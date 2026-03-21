"""
Backtesting engine for bruteforcecreativity.
This is infrastructure — the autonomous agent should NOT modify this file.

Usage:
    uv run backtest.py strategies/some_strategy.py

Loads a strategy module, runs its `run()` function against real market data,
computes performance metrics, and prints a structured summary.
"""

import sys
import importlib.util
import signal
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from fetch_data import DataFetcher

# ── Constants ────────────────────────────────────────────────────────

STARTING_CAPITAL = 10_000
BACKTEST_DAYS = 365
SLIPPAGE_PCT = 0.001  # 0.1% slippage per trade
TIMEOUT_SECONDS = 180  # 3 minute max per backtest


# ── Timeout handler ──────────────────────────────────────────────────

class BacktestTimeout(Exception):
    pass


def _timeout_handler(signum, frame):
    raise BacktestTimeout("Backtest exceeded 3 minute timeout")


# ── Metric computation ───────────────────────────────────────────────

def compute_metrics(
    portfolio_values: list[tuple],
    trades: list,
    starting_capital: float,
    risk_free_rate: float,
    spy_return_pct: float,
) -> dict:
    """
    Compute all performance metrics from a backtest result.

    Args:
        portfolio_values: list of (date, value) tuples
        trades: list of trade records
        starting_capital: initial capital
        risk_free_rate: annualized risk-free rate (decimal)
        spy_return_pct: SPY buy-and-hold return over same period (percent)

    Returns:
        dict with all metrics
    """
    if not portfolio_values or len(portfolio_values) < 2:
        return {
            "total_return_pct": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown_pct": 0.0,
            "win_rate_pct": 0.0,
            "num_trades": 0,
            "calmar_ratio": 0.0,
            "profit_factor": 0.0,
            "vs_spy_pct": -spy_return_pct,
        }

    dates, values = zip(*portfolio_values)
    values = np.array(values, dtype=float)

    # Total return
    final_value = values[-1]
    total_return_pct = ((final_value - starting_capital) / starting_capital) * 100

    # Daily returns
    daily_returns = np.diff(values) / values[:-1]

    # Sharpe ratio (annualized)
    if len(daily_returns) > 1 and np.std(daily_returns) > 0:
        daily_rf = risk_free_rate / 252
        excess_returns = daily_returns - daily_rf
        sharpe_ratio = (np.mean(excess_returns) / np.std(excess_returns)) * np.sqrt(252)
    else:
        sharpe_ratio = 0.0

    # Max drawdown
    peak = np.maximum.accumulate(values)
    drawdown = (values - peak) / peak
    max_drawdown_pct = np.min(drawdown) * 100

    # Win rate (from trades)
    if trades:
        # Try to pair buy/sell trades to compute wins
        wins = sum(1 for t in trades if isinstance(t, dict) and t.get("pnl", 0) > 0)
        closed = sum(1 for t in trades if isinstance(t, dict) and "pnl" in t)
        win_rate_pct = (wins / closed * 100) if closed > 0 else 0.0

        # Profit factor
        gross_profit = sum(t["pnl"] for t in trades if isinstance(t, dict) and t.get("pnl", 0) > 0)
        gross_loss = abs(sum(t["pnl"] for t in trades if isinstance(t, dict) and t.get("pnl", 0) < 0))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0
    else:
        win_rate_pct = 0.0
        profit_factor = 0.0

    # Calmar ratio
    if max_drawdown_pct != 0:
        calmar_ratio = total_return_pct / abs(max_drawdown_pct)
    else:
        calmar_ratio = float("inf") if total_return_pct > 0 else 0.0

    # vs SPY
    vs_spy_pct = total_return_pct - spy_return_pct

    return {
        "total_return_pct": round(total_return_pct, 2),
        "sharpe_ratio": round(sharpe_ratio, 2),
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "win_rate_pct": round(win_rate_pct, 1),
        "num_trades": len(trades),
        "calmar_ratio": round(calmar_ratio, 2),
        "profit_factor": round(profit_factor, 2),
        "vs_spy_pct": round(vs_spy_pct, 2),
    }


def get_spy_return(fetcher: DataFetcher, start: str, end: str) -> float:
    """Compute SPY buy-and-hold return for the benchmark period."""
    spy = fetcher.get_spy_benchmark(start=start, end=end)
    if spy.empty:
        return 0.0
    if isinstance(spy.columns, pd.MultiIndex):
        close = spy[("Close", "SPY")]
    elif "Close" in spy.columns:
        close = spy["Close"]
    else:
        return 0.0
    first = close.dropna().iloc[0]
    last = close.dropna().iloc[-1]
    return ((last - first) / first) * 100


# ── Main runner ──────────────────────────────────────────────────────

def run_backtest(strategy_path: str) -> dict:
    """
    Load and execute a strategy file's run() function.

    Returns dict with strategy metadata + performance metrics.
    """
    path = Path(strategy_path)
    if not path.exists():
        raise FileNotFoundError(f"Strategy file not found: {strategy_path}")

    # Dynamically import the strategy module
    spec = importlib.util.spec_from_file_location("strategy", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "run"):
        raise AttributeError(f"Strategy {path.name} must define a run() function")
    if not hasattr(module, "STRATEGY"):
        raise AttributeError(f"Strategy {path.name} must define a STRATEGY dict")

    strategy_meta = module.STRATEGY
    fetcher = DataFetcher()

    # Backtest period
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=BACKTEST_DAYS)).strftime("%Y-%m-%d")

    # Get risk-free rate and SPY benchmark
    risk_free_rate = fetcher.get_risk_free_rate()
    spy_return = get_spy_return(fetcher, start_date, end_date)

    # Set timeout
    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(TIMEOUT_SECONDS)

    try:
        start_time = time.time()
        result = module.run(fetcher, start_date, end_date, STARTING_CAPITAL)
        elapsed = time.time() - start_time
    finally:
        signal.alarm(0)  # Cancel timeout

    # Extract required fields from strategy result
    portfolio_values = result.get("portfolio_values", [])
    trades = result.get("trades", [])

    metrics = compute_metrics(
        portfolio_values=portfolio_values,
        trades=trades,
        starting_capital=STARTING_CAPITAL,
        risk_free_rate=risk_free_rate,
        spy_return_pct=spy_return,
    )

    return {
        "strategy_name": strategy_meta.get("name", path.stem),
        "elapsed_seconds": round(elapsed, 1),
        "spy_return_pct": round(spy_return, 2),
        **metrics,
    }


def print_summary(result: dict):
    """Print the structured summary block that the agent parses."""
    print("---")
    print(f"strategy:         {result['strategy_name']}")
    print(f"total_return_pct: {result['total_return_pct']}")
    print(f"sharpe_ratio:     {result['sharpe_ratio']}")
    print(f"max_drawdown_pct: {result['max_drawdown_pct']}")
    print(f"win_rate_pct:     {result['win_rate_pct']}")
    print(f"num_trades:       {result['num_trades']}")
    print(f"calmar_ratio:     {result['calmar_ratio']}")
    print(f"profit_factor:    {result['profit_factor']}")
    print(f"vs_spy_pct:       {result['vs_spy_pct']:+.2f}")
    print(f"spy_return_pct:   {result['spy_return_pct']}")
    print(f"elapsed_seconds:  {result['elapsed_seconds']}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: uv run backtest.py strategies/<name>.py")
        sys.exit(1)

    strategy_file = sys.argv[1]

    try:
        result = run_backtest(strategy_file)
        print_summary(result)
    except BacktestTimeout:
        print("---")
        print("strategy:         TIMEOUT")
        print("CRASHED: Backtest exceeded 3 minute timeout")
        sys.exit(1)
    except Exception as e:
        print("---")
        print(f"strategy:         CRASH")
        print(f"CRASHED: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
