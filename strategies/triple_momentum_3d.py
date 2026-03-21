"""
Triple Momentum 3d Lookback: Most responsive variant of GLD/QQQ/XLE rotation.
3-day lookback, 3-day rotation. Hypothesis: faster signals catch regime shifts
earliest, even if they generate more whipsaw noise.
"""

import pandas as pd

STRATEGY = {
    "name": "Triple Momentum 3d",
    "hypothesis": "3-day lookback is the most responsive, catching regime shifts earliest. More whipsaws but also earliest entry into new trends.",
    "universe": ["GLD", "QQQ", "XLE"],
    "entry": "Buy 3-day momentum leader among GLD/QQQ/XLE",
    "exit": "Rotate every 3 trading days",
    "position_size": "90% of cash",
    "eccentricity": "Ultra-fast cross-asset momentum rotation. Pure signal chasing at a frequency no institutional fund would attempt.",
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

    for i in range(3, len(common)):
        day = common[i]
        day_str = day.strftime("%Y-%m-%d") if hasattr(day, "strftime") else str(day)[:10]

        if current_holding:
            hold_counter += 1

        if hold_counter >= 3 or current_holding is None:
            lookback = common[i - 3]
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
