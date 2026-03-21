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
    - Daily portfolio values are reconstructed by replaying events against price data
    - Trade PnL and holding periods are computed by the engine via FIFO matching
    - Volume warnings flag unrealistic fills
    - Minimum trade count required for "winner" status
    - Out-of-sample split: first 9 months in-sample, last 3 months out-of-sample
"""

import logging
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

# ── Logging setup ────────────────────────────────────────────────────

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)


def setup_logging(strategy_name: str) -> logging.Logger:
    """Configure logging for a backtest run. Logs to both file and stderr."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = strategy_name.replace(" ", "_").replace("/", "_").lower()
    log_file = LOG_DIR / f"{timestamp}_{safe_name}.log"

    # Root logger for the bruteforce namespace
    logger = logging.getLogger("bruteforce")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    # File handler: everything (DEBUG+)
    fh = logging.FileHandler(log_file)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s %(name)-28s %(levelname)-5s %(message)s",
        datefmt="%H:%M:%S",
    ))
    logger.addHandler(fh)

    # Stderr handler: warnings and above only (keep terminal output clean)
    sh = logging.StreamHandler(sys.stderr)
    sh.setLevel(logging.WARNING)
    sh.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(sh)

    logger.info("Logging to %s", log_file)
    return logger


logger = logging.getLogger("bruteforce.backtest")


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
    """Compute all performance metrics from reconstructed daily portfolio values."""
    if not portfolio_values or len(portfolio_values) < 2:
        logger.warning("Not enough portfolio values to compute metrics (got %d)",
                        len(portfolio_values) if portfolio_values else 0)
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

    final_value = values[-1]
    total_return_pct = ((final_value - starting_capital) / starting_capital) * 100

    # Daily returns
    daily_returns = np.diff(values) / values[:-1]

    # Sharpe ratio (annualized)
    if len(daily_returns) > 1 and np.std(daily_returns) > 1e-10:
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
    if abs(max_drawdown_pct) > 0.01:
        calmar_ratio = total_return_pct / abs(max_drawdown_pct)
    else:
        calmar_ratio = float("inf") if total_return_pct > 0 else 0.0

    vs_spy_pct = total_return_pct - spy_return_pct

    logger.info("Metrics: return=%.2f%% sharpe=%.2f maxdd=%.2f%% vs_spy=%.2f%% trades=%d avg_hold=%.1fd",
                total_return_pct, sharpe_ratio, max_drawdown_pct, vs_spy_pct,
                trade_stats["num_trades"], trade_stats["avg_holding_days"])

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

    logger.info("OOS metrics (>= %s): %d trades, %.1f%% win rate, $%.2f PnL",
                oos_start, len(oos_trades),
                len(wins) / len(oos_trades) * 100 if oos_trades else 0, total_pnl)

    return {
        "oos_num_trades": len(oos_trades),
        "oos_win_rate_pct": round(len(wins) / len(oos_trades) * 100, 1),
        "oos_total_pnl": round(total_pnl, 2),
    }


def get_spy_return(fetcher: DataFetcher, start: str, end: str) -> float:
    """Compute SPY buy-and-hold return for the benchmark period."""
    spy = fetcher.get_spy_benchmark(start=start, end=end)
    if spy.empty:
        logger.warning("SPY benchmark data is empty")
        return 0.0
    if isinstance(spy.columns, pd.MultiIndex):
        close = spy[("Close", "SPY")]
    elif "Close" in spy.columns:
        close = spy["Close"]
    else:
        return 0.0
    first = close.dropna().iloc[0]
    last = close.dropna().iloc[-1]
    ret = ((last - first) / first) * 100
    logger.info("SPY benchmark: %.2f -> %.2f = %.2f%%", first, last, ret)
    return ret


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
        status = "loser"
    elif (vs_spy > 0 and sharpe > 1.0 and num_trades >= MIN_TRADES_FOR_WINNER
          and avg_hold <= MAX_AVG_HOLDING_DAYS_FOR_WINNER
          and oos_trades >= 2 and oos_pnl > 0):
        status = "winner"
    else:
        status = "mediocre"

    logger.info("Status: %s (vs_spy=%.2f sharpe=%.2f trades=%d avg_hold=%.1f oos_trades=%d oos_pnl=%.2f)",
                status, vs_spy, sharpe, num_trades, avg_hold, oos_trades, oos_pnl)
    return status


# ── Main runner ──────────────────────────────────────────────────────

def preload_prices(fetcher: DataFetcher, tickers: list[str], start: str, end: str) -> dict[str, pd.DataFrame]:
    """Pre-fetch price data for all tickers the strategy trades."""
    price_data = {}
    for ticker in tickers:
        try:
            df = fetcher.get_prices(ticker, start=start, end=end)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            price_data[ticker] = df
            logger.info("Loaded %d price rows for %s", len(df), ticker)
        except Exception as e:
            logger.error("Failed to load prices for %s: %s", ticker, e)
    return price_data


def run_backtest(strategy_path: str) -> dict:
    """
    Load and execute a strategy file's run() function with enforced Portfolio.

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
    strategy_name = strategy_meta.get("name", path.stem)

    # Set up logging for this run
    setup_logging(strategy_name)
    logger.info("=" * 60)
    logger.info("BACKTEST: %s", strategy_name)
    logger.info("File: %s", strategy_path)
    logger.info("Hypothesis: %s", strategy_meta.get("hypothesis", "N/A"))
    logger.info("Universe: %s", strategy_meta.get("universe", []))
    logger.info("=" * 60)

    fetcher = DataFetcher()

    # Backtest period
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=BACKTEST_DAYS)).strftime("%Y-%m-%d")
    oos_start = (datetime.now() - timedelta(days=OOS_SPLIT_MONTHS * 30)).strftime("%Y-%m-%d")

    logger.info("Period: %s to %s (OOS from %s)", start_date, end_date, oos_start)

    # Get risk-free rate and SPY benchmark
    risk_free_rate = fetcher.get_risk_free_rate()
    spy_return = get_spy_return(fetcher, start_date, end_date)
    logger.info("Risk-free rate: %.4f, SPY return: %.2f%%", risk_free_rate, spy_return)

    # Pre-load price data for the strategy's universe
    universe = strategy_meta.get("universe", [])
    if not universe:
        logger.warning("Strategy declares empty universe — no price data will be preloaded")
    price_data = preload_prices(fetcher, universe, start_date, end_date)

    # Create the Portfolio with enforced slippage
    portfolio = Portfolio(STARTING_CAPITAL, price_data)

    # Set timeout
    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(TIMEOUT_SECONDS)

    try:
        start_time = time.time()
        logger.info("Running strategy...")
        module.run(fetcher, portfolio, start_date, end_date)
        elapsed = time.time() - start_time
        logger.info("Strategy finished in %.1fs", elapsed)
    except BacktestTimeout:
        logger.error("Strategy TIMED OUT after %ds", TIMEOUT_SECONDS)
        raise
    except Exception as e:
        logger.error("Strategy CRASHED: %s: %s", type(e).__name__, e, exc_info=True)
        raise
    finally:
        signal.alarm(0)

    # Reconstruct daily portfolio values by replaying events
    portfolio_values = portfolio.reconstruct_daily_values()
    logger.info("Reconstructed %d daily portfolio values", len(portfolio_values))

    if portfolio_values:
        logger.info("Portfolio: $%.2f -> $%.2f", portfolio_values[0][1], portfolio_values[-1][1])

    # Extract metrics
    trade_stats = portfolio.get_trade_stats()
    volume_warnings = portfolio.get_volume_warnings()

    logger.info("Trade stats: %s", trade_stats)
    if volume_warnings:
        logger.warning("%d volume warnings", len(volume_warnings))

    metrics = compute_metrics(
        portfolio_values=portfolio_values,
        trade_stats=trade_stats,
        starting_capital=STARTING_CAPITAL,
        risk_free_rate=risk_free_rate,
        spy_return_pct=spy_return,
    )

    oos_metrics = compute_oos_metrics(portfolio.trades, oos_start)
    status = determine_status(metrics, oos_metrics)

    result = {
        "strategy_name": strategy_name,
        "elapsed_seconds": round(elapsed, 1),
        "spy_return_pct": round(spy_return, 2),
        "status": status,
        "volume_warnings": volume_warnings,
        **metrics,
        **oos_metrics,
    }

    logger.info("RESULT: %s — %s (return=%.2f%% vs_spy=%+.2f%%)",
                strategy_name, status, metrics["total_return_pct"], metrics["vs_spy_pct"])

    return result


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
