"""
Dual Lookback Relative Strength — buy only when both 5d AND 15d relative strength agree.

Uses the validated Rel Strength Quad assets (SLV/XLF/SOXX/GDX) but requires BOTH
the 5-day and 15-day relative strength vs SPY to be positive. Double confirmation
reduces false signals and whipsaw.

Score = min(5d alpha, 15d alpha). Buy the asset with the highest minimum alpha
(both timeframes strongly outperforming SPY). This ensures we only buy assets in
sustained outperformance, not just one-week flashes.
"""

import pandas as pd
import numpy as np

ASSETS = ["SLV", "XLF", "SOXX", "GDX"]

STRATEGY = {
    "name": "Dual Lookback Rel",
    "hypothesis": "Dual 5d + 15d relative strength confirmation. Both must agree for entry. Reduces false breakout signals.",
    "universe": ASSETS + ["SPY"],
    "entry": "Buy asset where both 5d and 15d relative strength vs SPY are positive. Highest min(5d,15d) alpha wins.",
    "exit": "Rotate every 3 days or -3% stop",
    "position_size": "90% of capital",
    "eccentricity": "Dual timeframe relative strength confirmation. Not just short-term or long-term — both must agree.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    prices = {}
    for a in ASSETS + ["SPY"]:
        df = data_fetcher.get_prices(a, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            prices[a] = s

    if len(prices) < 5:
        return

    common = None
    for s in prices.values():
        common = s.index if common is None else common.intersection(s.index)
    if common is None or len(common) < 20:
        return
    common = common.sort_values()

    pm = pd.DataFrame({a: prices[a].loc[common] for a in prices})
    ret5 = pm.pct_change(5)
    ret15 = pm.pct_change(15)

    current_holding = None
    rotation_day = 0
    entry_price = None

    for i in range(17, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        rotation_day += 1

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

        spy_ret5 = float(ret5["SPY"].iloc[i]) if pd.notna(ret5["SPY"].iloc[i]) else 0
        spy_ret15 = float(ret15["SPY"].iloc[i]) if pd.notna(ret15["SPY"].iloc[i]) else 0

        best_asset = None
        best_min_alpha = 0

        for asset in ASSETS:
            a5 = float(ret5[asset].iloc[i]) if pd.notna(ret5[asset].iloc[i]) else 0
            a15 = float(ret15[asset].iloc[i]) if pd.notna(ret15[asset].iloc[i]) else 0

            alpha5 = a5 - spy_ret5
            alpha15 = a15 - spy_ret15

            # Both must be positive
            if alpha5 > 0 and alpha15 > 0:
                min_alpha = min(alpha5, alpha15)
                if min_alpha > best_min_alpha:
                    best_min_alpha = min_alpha
                    best_asset = asset

        target = best_asset

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
