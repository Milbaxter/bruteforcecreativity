"""
Relative Strength GDX Trio — SPY relative strength rotation with gold miners.

Thesis: Same framework as SPY Rel Strength Alpha (validated winner) but with GDX
(gold miners) replacing SLV. Gold miners offer:
- Higher beta to gold price (leveraged gold exposure)
- Equity-like returns during gold rallies
- Better relative strength signals because moves are more dramatic

Universe: GDX (gold miners), XLF (banks), SOXX (semiconductors)
Buy whichever has the highest 10-day relative strength vs SPY.
Only buy if outperforming SPY.

3-day rotation with -3% stop loss.
"""

import pandas as pd
import numpy as np

ASSETS = ["GDX", "XLF", "SOXX"]

STRATEGY = {
    "name": "Rel Strength GDX Trio",
    "hypothesis": "GDX/XLF/SOXX relative strength vs SPY. Gold miners replace silver for higher beta commodity exposure. Buy the biggest SPY outperformer.",
    "universe": ASSETS + ["SPY"],
    "entry": "Buy asset with highest 10d return vs SPY if outperforming. Cash if none beating SPY.",
    "exit": "Rotate every 3 days or -3% stop",
    "position_size": "90% of capital",
    "eccentricity": "Gold miners (not gold ETF) as commodity component in relative strength rotation. GDX has equity-like beta to gold, creating stronger signals.",
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

        best_asset = None
        best_alpha = 0

        for asset in ASSETS:
            asset_ret = float(ret10[asset].iloc[i]) if pd.notna(ret10[asset].iloc[i]) else 0
            alpha = asset_ret - spy_ret
            if alpha > best_alpha:
                best_alpha = alpha
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
