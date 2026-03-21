"""
Backtesting engine for bruteforcecreativity.
This is infrastructure — the autonomous agent should NOT modify this file.

Usage:
    uv run backtest.py strategies/some_strategy.py

Loads a strategy module, passes it a Portfolio object with enforced slippage,
runs it against real market data, computes performance metrics, and prints
a structured summary.

Critical properties:
    - Slippage is enforced by the Portfolio, not the strategy
    - Daily portfolio values are recorded by the engine, not the strategy
    - Trade PnL and holding periods are computed by the engine via FIFO matching
    - Volume warnings flag unrealistic fills
    - Minimum trade count required for "winner" status
    - Out-of-sample split: first 9 months in-sample, last 3 months out-of-sample
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
from portfolio import Portfolio

# ── Constants ────────────────────────────────────────────────────────

STARTING_CAPITAL = 10_000
BACKTEST_DAYS = 365
TIMEOUT_SECONDS = 180  # 3 minute max per backtest
MIN_TRADES_FOR_WINNER = 8  # Need at least this many round-trip trades
MAX_AVG_HOLDING_DAYS_FOR_WINNER = 15  # Prefer fast in-and-out
OOS_SPLIT_MONTHS = 3  # Last 3 months are out-of-sample


# ── Timeout handler ──────────────────────────────────────────────────

class BacktestTimeout(Exception):
    pass


def _timeout_handler(signum, frame):
    raise BacktestTimeout("Backtest exceeded 3 minute timeout")


# ── Metric computation ───────────────────────────────────────────────

def compute_metrics(
    portfolio_values: list[tuple[str, float]],
    trade_stats: dict,
    starting_capital: float,
    risk_free_rate: float,
    spy_return_pct: float,
) -> dict:
    """
    Compute all performance metrics from portfolio values and trade stats.
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
            "avg_holding_days": 0.0,
            "max_holding_days": 0,
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
        "win_rate_pct": trade_stats["win_rate_pct"],
        "num_trades": trade_stats["num_trades"],
        "calmar_ratio": round(calmar_ratio, 2),
        "profit_factor": trade_stats["profit_factor"],
        "avg_holding_days": trade_stats["avg_holding_days"],
        "max_holding_days": trade_stats["max_holding_days"],
        "vs_spy_pct": round(vs_spy_pct, 2),
    }


def compute_oos_metrics(trades: list[dict], oos_start: str) -> dict:
    """Compute metrics for out-of-sample period (trades after oos_start)."""
    oos_trades = [t for t in trades if t.get("date", "") >= oos_start]
    if not oos_trades:
        return {"oos_num_trades": 0, "oos_win_rate_pct": 0.0, "oos_total_pnl": 0.0}

    wins = [t for t in oos_trades if t.get("pnl", 0) > 0]
    total_pnl = sum(t.get("pnl", 0) for t in oos_trades)

    return {
        "oos_num_trades": len(oos_trades),
        "oos_win_rate_pct": round(len(wins) / len(oos_trades) * 100, 1),
        "oos_total_pnl": round(total_pnl, 2),
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


def determine_status(metrics: dict, oos_metrics: dict) -> str:
    """
    Determine strategy status based on metrics.

    winner:   beats SPY, Sharpe > 1.0, min trades met, avg holding <= 15 days,
              AND has out-of-sample trades with positive PnL
    mediocre: positive return but doesn't meet winner criteria
    loser:    negative return or worse than SPY by > 5%
    """
    num_trades = metrics["num_trades"]
    total_return = metrics["total_return_pct"]
    sharpe = metrics["sharpe_ratio"]
    vs_spy = metrics["vs_spy_pct"]
    avg_hold = metrics["avg_holding_days"]
    oos_pnl = oos_metrics.get("oos_total_pnl", 0)
    oos_trades = oos_metrics.get("oos_num_trades", 0)

    if total_return < 0 or vs_spy < -5:
        return "loser"

    is_winner = (
        vs_spy > 0
        and sharpe > 1.0
        and num_trades >= MIN_TRADES_FOR_WINNER
        and avg_hold <= MAX_AVG_HOLDING_DAYS_FOR_WINNER
        and oos_trades >= 2
        and oos_pnl > 0
    )

    return "winner" if is_winner else "mediocre"


# ── Main runner ──────────────────────────────────────────────────────

def preload_prices(fetcher: DataFetcher, tickers: list[str], start: str, end: str) -> dict[str, pd.DataFrame]:
    """Pre-fetch price data for all tickers the strategy trades."""
    price_data = {}
    for ticker in tickers:
        try:
            df = fetcher.get_prices(ticker, start=start, end=end)
            if isinstance(df.columns, pd.MultiIndex):
                # Flatten for single ticker
                df.columns = df.columns.get_level_values(0)
            price_data[ticker] = df
        except Exception:
            pass  # Ticker not found — strategy will get None from portfolio
    return price_data


def run_backtest(strategy_path: str) -> dict:
    """
    Load and execute a strategy file's run() function with enforced Portfolio.

    The strategy receives:
        - data_fetcher: DataFetcher instance (for fetching any data)
        - portfolio: Portfolio instance (for executing trades with enforced slippage)
        - start_date: str
        - end_date: str

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

    # Out-of-sample split date
    oos_start = (datetime.now() - timedelta(days=OOS_SPLIT_MONTHS * 30)).strftime("%Y-%m-%d")

    # Get risk-free rate and SPY benchmark
    risk_free_rate = fetcher.get_risk_free_rate()
    spy_return = get_spy_return(fetcher, start_date, end_date)

    # Pre-load price data for the strategy's universe
    universe = strategy_meta.get("universe", [])
    price_data = preload_prices(fetcher, universe, start_date, end_date)

    # Create the Portfolio with enforced slippage
    portfolio = Portfolio(STARTING_CAPITAL, price_data)

    # Set timeout
    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(TIMEOUT_SECONDS)

    try:
        start_time = time.time()
        # Strategy uses portfolio.buy() / portfolio.sell() to trade
        module.run(fetcher, portfolio, start_date, end_date)
        elapsed = time.time() - start_time
    finally:
        signal.alarm(0)  # Cancel timeout

    # Record daily portfolio values across the full period
    all_dates = set()
    for ticker, df in price_data.items():
        for dt in df.index:
            all_dates.add(dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(dt)[:10])

    for date_str in sorted(all_dates):
        portfolio.record_daily_value(date_str)

    # Extract metrics
    portfolio_values = portfolio.get_portfolio_values()
    trade_stats = portfolio.get_trade_stats()
    volume_warnings = portfolio.get_volume_warnings()

    metrics = compute_metrics(
        portfolio_values=portfolio_values,
        trade_stats=trade_stats,
        starting_capital=STARTING_CAPITAL,
        risk_free_rate=risk_free_rate,
        spy_return_pct=spy_return,
    )

    # Out-of-sample metrics
    oos_metrics = compute_oos_metrics(portfolio.trades, oos_start)

    # Determine status
    status = determine_status(metrics, oos_metrics)

    return {
        "strategy_name": strategy_meta.get("name", path.stem),
        "elapsed_seconds": round(elapsed, 1),
        "spy_return_pct": round(spy_return, 2),
        "status": status,
        "volume_warnings": volume_warnings,
        **metrics,
        **oos_metrics,
    }


def print_summary(result: dict):
    """Print the structured summary block that the agent parses."""
    print("---")
    print(f"strategy:          {result['strategy_name']}")
    print(f"status:            {result['status']}")
    print(f"total_return_pct:  {result['total_return_pct']}")
    print(f"sharpe_ratio:      {result['sharpe_ratio']}")
    print(f"max_drawdown_pct:  {result['max_drawdown_pct']}")
    print(f"win_rate_pct:      {result['win_rate_pct']}")
    print(f"num_trades:        {result['num_trades']}")
    print(f"avg_holding_days:  {result['avg_holding_days']}")
    print(f"max_holding_days:  {result['max_holding_days']}")
    print(f"calmar_ratio:      {result['calmar_ratio']}")
    print(f"profit_factor:     {result['profit_factor']}")
    print(f"vs_spy_pct:        {result['vs_spy_pct']:+.2f}")
    print(f"spy_return_pct:    {result['spy_return_pct']}")
    print(f"oos_num_trades:    {result['oos_num_trades']}")
    print(f"oos_win_rate_pct:  {result['oos_win_rate_pct']}")
    print(f"oos_total_pnl:     {result['oos_total_pnl']}")
    print(f"elapsed_seconds:   {result['elapsed_seconds']}")

    if result.get("volume_warnings"):
        print(f"volume_warnings:   {len(result['volume_warnings'])}")
        for w in result["volume_warnings"][:5]:
            print(f"  WARN: {w}")


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
