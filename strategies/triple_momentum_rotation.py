"""
Triple Momentum Rotation: Rotate between GLD (gold), QQQ (tech), and XLE (energy)
every 3 trading days, always holding the one with strongest 5-day momentum.

Thesis: These three asset classes represent the three major market regimes:
- QQQ: risk-on / growth / AI narrative
- GLD: risk-off / inflation hedge / geopolitical fear
- XLE: energy supercycle / inflation / commodity boom

At any given time, one of these is the dominant narrative. By rotating
into the 5-day momentum leader every 3 days, we catch regime shifts early.
"""

import pandas as pd

STRATEGY = {
    "name": "Triple Momentum Rotation",
    "hypothesis": "QQQ, GLD, and XLE represent three distinct market regimes. The 5-day momentum leader captures the dominant narrative. 3-day rotation catches shifts early.",
    "universe": ["GLD", "QQQ", "XLE"],
    "entry": "Buy whichever of GLD, QQQ, XLE has highest 5-day momentum",
    "exit": "Rotate every 3 trading days to the current momentum leader",
    "position_size": "90% of cash in the leader",
    "eccentricity": "Three-way cross-asset rotation at daytrader speed. No fund rotates between gold, tech, and energy every 3 days. Too domain-crossing for any single-mandate fund.",
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

    for i in range(5, len(common)):
        day = common[i]
        day_str = day.strftime("%Y-%m-%d") if hasattr(day, "strftime") else str(day)[:10]

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

            if not momentum:
                continue

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
