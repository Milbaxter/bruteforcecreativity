"""
Five Asset Momentum: Expand the winning Triple Momentum Rotation to 5 assets:
GLD (gold), QQQ (tech), XLE (energy), TLT (bonds), UNG (natural gas).

More asset classes = more regime diversity. Adding bonds captures the
flight-to-safety trade, and natural gas captures commodity volatility
(weather events, supply shocks).
"""

import pandas as pd

STRATEGY = {
    "name": "Five Asset Momentum",
    "hypothesis": "Five uncorrelated asset classes (gold, tech, energy, bonds, nat gas) always have one dominant momentum theme. Rotating into the 5-day leader captures whatever narrative is hot.",
    "universe": ["GLD", "QQQ", "XLE", "TLT", "UNG"],
    "entry": "Buy the asset with highest 5-day momentum every 3 trading days",
    "exit": "Rotate every 3 trading days",
    "position_size": "90% of cash in the leader",
    "eccentricity": "Five-way cross-asset rotation. No institutional fund would rotate between gold, tech, energy, bonds, and natural gas every 3 days. Too schizophrenic for any mandate.",
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
