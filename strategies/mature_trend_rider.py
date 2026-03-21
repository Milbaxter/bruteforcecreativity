"""
Mature Trend Rider — buy assets with established but decelerating positive trends.

Thesis: The best time to enter a trend isn't at the start (too volatile, many false
starts) or at the end (reversal risk). It's in the MIDDLE — when the trend is well
established (10d return is solidly positive) but starting to slow down slightly (5d < 10d).
This "mature trend" phase is where the highest risk-adjusted returns occur because:
(1) the trend is confirmed by time and magnitude, (2) volatility has dropped, (3)
late momentum chasers haven't piled in yet because the trend looks "old."

Entry criteria per asset:
- 10d return > 2% (strong established trend)
- 5d return > 0 but < 10d return (decelerating = mature, not reversal)
- 20d return > 0 (longer-term trend support)

Rotate into the asset with the best 10d return (strongest established trend).
"""

import pandas as pd
import numpy as np

ASSETS = ["QQQ", "EEM", "TLT", "BITO", "XLF"]

STRATEGY = {
    "name": "Mature Trend Rider",
    "hypothesis": "Assets with strong 10d return, positive but decelerating 5d return, and positive 20d trend are in a sweet spot. Ride the established trend until it fades.",
    "universe": ASSETS + ["SPY"],
    "entry": "Buy asset with 10d return > 2%, 5d return positive but < 10d, 20d return > 0. Best 10d return wins.",
    "exit": "Rotate every 3 days. Cash if no qualifying asset.",
    "position_size": "90% of capital",
    "eccentricity": "Trend maturity detection (not just direction). Avoids the noisy early trend and the dangerous late trend by targeting the stable middle phase.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    prices = {}
    for a in ASSETS:
        df = data_fetcher.get_prices(a, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            prices[a] = s

    if len(prices) < 3:
        return

    common = None
    for s in prices.values():
        common = s.index if common is None else common.intersection(s.index)
    if common is None or len(common) < 25:
        return
    common = common.sort_values()

    pm = pd.DataFrame({a: prices[a].loc[common] for a in prices})

    ret_5d = pm.pct_change(5)
    ret_10d = pm.pct_change(10)
    ret_20d = pm.pct_change(20)

    current_holding = None
    rotation_day = 0

    for i in range(22, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        rotation_day += 1

        if rotation_day < 3 and current_holding is not None:
            continue

        best_asset = None
        best_10d = 0

        for asset in prices.keys():
            r5 = float(ret_5d[asset].iloc[i]) if pd.notna(ret_5d[asset].iloc[i]) else 0
            r10 = float(ret_10d[asset].iloc[i]) if pd.notna(ret_10d[asset].iloc[i]) else 0
            r20 = float(ret_20d[asset].iloc[i]) if pd.notna(ret_20d[asset].iloc[i]) else 0

            # Mature trend: strong 10d, positive but decelerating 5d, positive 20d
            if r10 > 0.02 and r5 > 0 and r5 < r10 and r20 > 0:
                if r10 > best_10d:
                    best_10d = r10
                    best_asset = asset

        target = best_asset

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
