"""
Multi-Timeframe Consensus — rotate into the asset where 3d, 5d, and 10d momentum agree.

Thesis: When an asset shows positive momentum across ALL three timeframes (3-day, 5-day,
10-day), the trend is robust and likely to continue. Single-timeframe momentum is noisy;
triple-timeframe consensus filters out false signals. Among a diverse asset universe,
buy the one with the strongest consensus signal (highest average rank across timeframes).

Universe: QQQ, KWEB, EEM, XBI, ARKK — high-beta, diverse growth assets where momentum
tends to persist. Not the usual GLD/QQQ/XLE rotation.

Rotation every 3 days. Only enter if at least one asset has positive momentum across
all three timeframes. Otherwise sit in cash.
"""

import pandas as pd
import numpy as np

ASSETS = ["QQQ", "KWEB", "EEM", "XBI", "ARKK"]

STRATEGY = {
    "name": "Multi-TF Consensus",
    "hypothesis": "When 3d, 5d, and 10d momentum all agree for an asset, trend continuation is strong. Rotate into the asset with the best consensus across diverse high-beta universe.",
    "universe": ASSETS + ["SPY"],
    "entry": "Buy asset where 3d, 5d, and 10d returns are all positive and avg rank is highest. Rotate every 3 days.",
    "exit": "Rotate every 3 days. Cash if no asset has consensus.",
    "position_size": "90% of capital",
    "eccentricity": "Multi-timeframe momentum consensus across diverse high-beta growth assets (not vanilla sector rotation). Triple-confirmation reduces false signals.",
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

    # Common dates
    common = None
    for s in prices.values():
        common = s.index if common is None else common.intersection(s.index)
    if len(common) < 15:
        return
    common = common.sort_values()

    pm = pd.DataFrame({a: prices[a].loc[common] for a in prices})

    # Multi-timeframe returns
    ret_3d = pm.pct_change(3)
    ret_5d = pm.pct_change(5)
    ret_10d = pm.pct_change(10)

    current_holding = None
    rotation_day = 0

    for i in range(12, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        rotation_day += 1

        if rotation_day < 3 and current_holding is not None:
            continue

        # Evaluate consensus for each asset
        best_asset = None
        best_score = -999

        for asset in prices.keys():
            r3 = float(ret_3d[asset].iloc[i]) if pd.notna(ret_3d[asset].iloc[i]) else 0
            r5 = float(ret_5d[asset].iloc[i]) if pd.notna(ret_5d[asset].iloc[i]) else 0
            r10 = float(ret_10d[asset].iloc[i]) if pd.notna(ret_10d[asset].iloc[i]) else 0

            # All three must be positive (consensus)
            if r3 > 0 and r5 > 0 and r10 > 0:
                # Score: average of all three returns
                score = (r3 + r5 + r10) / 3
                if score > best_score:
                    best_score = score
                    best_asset = asset

        target = best_asset  # None if no consensus found

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
