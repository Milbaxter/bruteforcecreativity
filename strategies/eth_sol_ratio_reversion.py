"""
ETH SOL Ratio Reversion — pairs-style mean reversion between ETH and SOL.

When the ETH/SOL price ratio deviates significantly from its recent mean,
buy the underperformer expecting ratio convergence. Pure crypto play.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "ETH SOL Ratio Reversion",
    "hypothesis": "ETH and SOL are correlated crypto assets. When their price ratio deviates >1.5 std from the 20-day mean, the laggard tends to catch up. This is a classic pairs/stat-arb pattern applied to crypto.",
    "universe": ["ETH-USD", "SOL-USD"],
    "entry": "Buy the underperformer when ETH/SOL ratio z-score exceeds 1.5 std from 20d mean, crypto fear/greed between 20-80",
    "exit": "Sell when ratio z-score reverts below 0.5 std, or after 7 days, or on -5% stop",
    "position_size": "90% of available cash per trade",
    "eccentricity": "Crypto pairs trading at retail scale — institutional crypto desks exist but don't touch altcoin pairs at this size. Uses sentiment filter to avoid trading during panic/euphoria.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Fetch crypto prices
    eth = data_fetcher.get_prices("ETH-USD", start=start_date, end=end_date)
    sol = data_fetcher.get_prices("SOL-USD", start=start_date, end=end_date)

    if isinstance(eth.columns, pd.MultiIndex):
        eth.columns = eth.columns.get_level_values(0)
    if isinstance(sol.columns, pd.MultiIndex):
        sol.columns = sol.columns.get_level_values(0)

    if eth.empty or sol.empty:
        return

    # Get crypto fear/greed
    try:
        fear_greed = data_fetcher.get_crypto_fear_greed(days=400)
    except Exception:
        fear_greed = None

    # Align dates
    common_dates = eth.index.intersection(sol.index)
    if len(common_dates) < 25:
        return

    eth = eth.loc[common_dates]
    sol = sol.loc[common_dates]

    # Compute ratio
    ratio = eth["Close"] / sol["Close"]

    trading_days = sorted(common_dates)
    lookback = 20
    z_entry = 1.5
    z_exit = 0.5
    max_hold = 7
    stop_loss = -0.05

    in_trade = False
    trade_ticker = None
    entry_price = None
    entry_idx = None

    for i in range(lookback, len(trading_days)):
        day = trading_days[i]
        date_str = day.strftime("%Y-%m-%d") if hasattr(day, "strftime") else str(day)[:10]

        # Check fear/greed filter
        if fear_greed is not None and not fear_greed.empty:
            fg_before = fear_greed[fear_greed.index <= day]
            if len(fg_before) > 0:
                fg_val = float(fg_before.iloc[-1])
                if fg_val < 20 or fg_val > 80:
                    # Extreme sentiment — close any position and skip
                    if in_trade and trade_ticker in portfolio.positions:
                        portfolio.sell(trade_ticker, all_shares=True, date=date_str)
                        in_trade = False
                        trade_ticker = None
                    continue

        # Compute z-score of ratio
        window = ratio.iloc[i - lookback:i]
        mean_ratio = window.mean()
        std_ratio = window.std()
        if std_ratio < 1e-10:
            continue
        current_ratio = ratio.iloc[i]
        z_score = (current_ratio - mean_ratio) / std_ratio

        if in_trade:
            # Check exit conditions
            days_held = i - entry_idx
            current_price = float(eth.loc[day, "Close"]) if trade_ticker == "ETH-USD" else float(sol.loc[day, "Close"])

            pnl_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0

            should_exit = False
            if abs(z_score) < z_exit:  # ratio reverted
                should_exit = True
            elif days_held >= max_hold:  # time stop
                should_exit = True
            elif pnl_pct <= stop_loss:  # stop loss
                should_exit = True

            if should_exit and trade_ticker in portfolio.positions:
                portfolio.sell(trade_ticker, all_shares=True, date=date_str)
                in_trade = False
                trade_ticker = None
                entry_price = None
                entry_idx = None
        else:
            # Check entry conditions
            if z_score > z_entry:
                # ETH overvalued relative to SOL — buy SOL
                trade_ticker = "SOL-USD"
                entry_price = float(sol.loc[day, "Close"])
                portfolio.buy(trade_ticker, dollars=portfolio.cash * 0.90, date=date_str)
                in_trade = True
                entry_idx = i
            elif z_score < -z_entry:
                # SOL overvalued relative to ETH — buy ETH
                trade_ticker = "ETH-USD"
                entry_price = float(eth.loc[day, "Close"])
                portfolio.buy(trade_ticker, dollars=portfolio.cash * 0.90, date=date_str)
                in_trade = True
                entry_idx = i

    # Close any open position
    if in_trade and trade_ticker and trade_ticker in portfolio.positions:
        end_str = trading_days[-1].strftime("%Y-%m-%d") if hasattr(trading_days[-1], "strftime") else str(trading_days[-1])[:10]
        portfolio.sell(trade_ticker, all_shares=True, date=end_str)
