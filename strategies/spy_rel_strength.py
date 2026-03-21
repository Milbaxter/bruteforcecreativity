"""
SPY Relative Strength Alpha — buy the asset most outperforming SPY.

Thesis: Instead of absolute momentum, use RELATIVE STRENGTH vs SPY. Buy the asset
that is beating the broad market by the most over 10 days. If it's outperforming SPY,
it has something special going on (sector-specific catalyst) that will continue.

Universe: SLV (commodity), XLF (banks), SOXX (semis) — three unrelated sectors.
SPY is the benchmark, not a trading asset.

Only buy if the best asset has positive relative strength (actually beating SPY).
If none is beating SPY, go to cash (the broad market is the place to be).

3-day rotation, -3% stop loss.
"""

import pandas as pd
import numpy as np

ASSETS = ["SLV", "XLF", "SOXX"]

STRATEGY = {
    "name": "SPY Rel Strength Alpha",
    "hypothesis": "Buy the asset most outperforming SPY over 10 days. Relative strength captures sector-specific catalysts that persist.",
    "universe": ASSETS + ["SPY"],
    "entry": "Buy asset with highest 10d return vs SPY, if positive. Cash if none beating SPY.",
    "exit": "Rotate every 3 days or -3% stop",
    "position_size": "90% of capital",
    "eccentricity": "Relative strength vs SPY (not absolute momentum) for sector selection. Captures alpha above the market, not just raw returns.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    prices = {}
    for a in ASSETS + ["SPY"]:
        df = data_fetcher.get_prices(a, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            prices[a] = s

    if len(prices) < 4:
        return

    common = None
    for s in prices.values():
        common = s.index if common is None else common.intersection(s.index)
    if common is None or len(common) < 15:
        return
    common = common.sort_values()

    pm = pd.DataFrame({a: prices[a].loc[common] for a in prices})
    ret10 = pm.pct_change(10)

    current_holding = None
    rotation_day = 0
    entry_price = None

    for i in range(12, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        rotation_day += 1

        # Stop loss
        if current_holding and entry_price:
            curr = float(pm[current_holding].iloc[i])
            pnl_pct = (curr - entry_price) / entry_price
            if pnl_pct <= -0.03:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
                current_holding = None
                entry_price = None
                rotation_day = 0
                continue

        if rotation_day < 3 and current_holding is not None:
            continue

        spy_ret = float(ret10["SPY"].iloc[i]) if pd.notna(ret10["SPY"].iloc[i]) else 0

        # Find best relative strength vs SPY
        best_asset = None
        best_alpha = 0

        for asset in ASSETS:
            asset_ret = float(ret10[asset].iloc[i]) if pd.notna(ret10[asset].iloc[i]) else 0
            alpha = asset_ret - spy_ret

            if alpha > best_alpha:
                best_alpha = alpha
                best_asset = asset

        target = best_asset  # None if no asset is beating SPY

        if target != current_holding:
            if current_holding:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
            if target:
                result = portfolio.buy(target, dollars=portfolio.cash * 0.9, date=date_str)
                if result:
                    entry_price = float(pm[target].iloc[i])
            current_holding = target
            rotation_day = 0

    if current_holding:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(current_holding, all_shares=True, date=last_date)
