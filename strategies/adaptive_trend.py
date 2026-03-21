"""
Adaptive Trend — VIX-adaptive moving average for QQQ/SLV/XLF trend following.

Thesis: Fixed-period moving averages suffer from a fundamental tradeoff: short periods
catch trends early but whipsaw in noise; long periods are robust but late.

Solution: Adapt the lookback period based on VIX:
- VIX < 18 (calm): Use 5-day fast MA vs 15-day slow MA (catch trends quickly)
- VIX 18-25 (moderate): Use 7-day fast MA vs 20-day slow MA (balanced)
- VIX > 25 (volatile): Use 10-day fast MA vs 30-day slow MA (filter noise)

For each of QQQ, SLV, XLF: if fast MA > slow MA → trend is UP. Buy the asset with
the strongest uptrend (biggest fast-slow gap relative to price). Cash if no asset
has an uptrend.

3-day rotation cycle.
"""

import pandas as pd
import numpy as np

ASSETS = ["QQQ", "SLV", "XLF"]

STRATEGY = {
    "name": "Adaptive Trend",
    "hypothesis": "VIX-adaptive moving average crossover: short lookback in calm markets, long in volatile. Buy asset with strongest uptrend. QQQ/SLV/XLF universe.",
    "universe": ASSETS + ["SPY"],
    "entry": "Buy asset where adaptive fast MA > slow MA with biggest gap. VIX sets MA periods.",
    "exit": "Rotate every 3 days. Cash if no uptrend.",
    "position_size": "90% of capital",
    "eccentricity": "VIX-adaptive moving average periods. Automatically adjusts trend sensitivity to market conditions. No fixed lookback period.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    vix = data_fetcher.get_vix(start=start_date, end=end_date)
    prices = {}
    for a in ASSETS:
        df = data_fetcher.get_prices(a, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            prices[a] = s

    if len(prices) < 3 or vix.empty:
        return

    vix.index = pd.to_datetime(vix.index)
    common = None
    for s in prices.values():
        common = s.index if common is None else common.intersection(s.index)
    common = common.intersection(vix.index)
    if common is None or len(common) < 35:
        return
    common = common.sort_values()

    pm = pd.DataFrame({a: prices[a].loc[common] for a in prices})
    vix_c = vix.loc[common]

    current_holding = None
    rotation_day = 0

    for i in range(35, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        rotation_day += 1

        if rotation_day < 3 and current_holding is not None:
            continue

        v = float(vix_c.iloc[i])

        # Adaptive MA periods
        if v < 18:
            fast_period, slow_period = 5, 15
        elif v <= 25:
            fast_period, slow_period = 7, 20
        else:
            fast_period, slow_period = 10, 30

        # Score each asset
        best_asset = None
        best_gap = 0

        for asset in prices:
            fast_ma = float(pm[asset].iloc[i-fast_period+1:i+1].mean())
            slow_ma = float(pm[asset].iloc[i-slow_period+1:i+1].mean())
            price = float(pm[asset].iloc[i])

            if fast_ma > slow_ma:
                gap = (fast_ma - slow_ma) / price  # normalized gap
                if gap > best_gap:
                    best_gap = gap
                    best_asset = asset

        target = best_asset  # None if no uptrends

        if target != current_holding:
            if current_holding:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
            if target:
                portfolio.buy(target, dollars=portfolio.cash * 0.9, date=date_str)
            current_holding = target
            rotation_day = 0

    if current_holding:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(current_holding, all_shares=True, date=last_date)
