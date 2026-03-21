"""
Monthly Rebalance Momentum: At the start of each month, go all-in on the ETF
with the best prior-month return from a diverse basket. Hold for the month.

Thesis: Monthly momentum is one of the most robust anomalies in finance.
Assets that performed well last month tend to continue. By rebalancing monthly
with a diverse basket, we capture the dominant theme of each month.

We use a basket of: QQQ (tech), GLD (gold), XLE (energy), XLV (healthcare),
XLF (financials), SPY (broad market).
"""

import pandas as pd

STRATEGY = {
    "name": "Monthly Rebalance Momentum",
    "hypothesis": "Monthly momentum persistence across diverse asset classes captures the dominant narrative each month. Simple but effective.",
    "universe": ["QQQ", "GLD", "XLE", "XLV", "XLF", "SPY"],
    "entry": "At month start, buy the ETF with best prior 20-day return",
    "exit": "Sell and rotate at next month start (~20 trading days)",
    "position_size": "90% of cash",
    "eccentricity": "Monthly cross-sector momentum rotation using price signals only. Too simplistic for quant funds, too frequent for passive allocation models.",
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
    if len(common) < 25:
        return

    current_holding = None
    hold_counter = 0
    rotation_period = 20  # ~1 month of trading days

    for i in range(20, len(common)):
        day = common[i]
        day_str = day.strftime("%Y-%m-%d") if hasattr(day, "strftime") else str(day)[:10]

        if current_holding:
            hold_counter += 1

        if hold_counter >= rotation_period or current_holding is None:
            lookback = common[i - 20]
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
                    hold_counter = 0

    if current_holding and common:
        last = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(current_holding, all_shares=True, date=last)
