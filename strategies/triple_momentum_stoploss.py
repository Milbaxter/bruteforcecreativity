"""
Triple Momentum with Stop Loss: Same GLD/QQQ/XLE rotation with 5-day lookback,
but adds a -3% stop loss per holding period. If the current position drops 3%
from entry, sell immediately and switch to the next best momentum leader.
"""

import pandas as pd

STRATEGY = {
    "name": "Triple Momentum StopLoss",
    "hypothesis": "Adding a -3% stop loss to the Triple Momentum Rotation reduces drawdowns and improves Sharpe by cutting losers quickly while letting winners ride.",
    "universe": ["GLD", "QQQ", "XLE"],
    "entry": "Buy 5-day momentum leader among GLD/QQQ/XLE",
    "exit": "Rotate every 3 days, or immediately if position drops -3% from entry",
    "position_size": "90% of cash",
    "eccentricity": "Momentum rotation with active risk management. The stop loss prevents holding through regime-change drawdowns.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    universe = STRATEGY["universe"]
    all_prices = {}
    for ticker in universe:
        p = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
        if isinstance(p.columns, pd.MultiIndex):
            p.columns = p.columns.get_level_values(0)
        if not p.empty and "Close" in p.columns:
            all_prices[ticker] = p["Close"]

    if len(all_prices) < 3:
        return

    common = sorted(set.intersection(*[set(s.index) for s in all_prices.values()]))
    if len(common) < 10:
        return

    current_holding = None
    hold_counter = 0
    entry_price = None

    for i in range(5, len(common)):
        day = common[i]
        day_str = day.strftime("%Y-%m-%d") if hasattr(day, "strftime") else str(day)[:10]

        # Check stop loss first
        if current_holding and entry_price:
            current_price = float(all_prices[current_holding].loc[day])
            pct_change = (current_price - entry_price) / entry_price

            if pct_change <= -0.03:
                portfolio.sell(current_holding, all_shares=True, date=day_str)
                current_holding = None
                entry_price = None
                hold_counter = 0
                # Fall through to entry logic

        if current_holding:
            hold_counter += 1

        if hold_counter >= 3 or current_holding is None:
            lookback = common[i - 5]
            momentum = {}
            for ticker, series in all_prices.items():
                cur = float(series.loc[day])
                prev = float(series.loc[lookback])
                if prev > 0:
                    momentum[ticker] = (cur - prev) / prev

            target = max(momentum, key=momentum.get)

            if current_holding and current_holding != target:
                portfolio.sell(current_holding, all_shares=True, date=day_str)
                current_holding = None

            if current_holding is None:
                result = portfolio.buy(target, dollars=portfolio.cash * 0.90, date=day_str)
                if result:
                    current_holding = target
                    entry_price = float(all_prices[target].loc[day])
                    hold_counter = 0

    if current_holding and common:
        last = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(current_holding, all_shares=True, date=last)
