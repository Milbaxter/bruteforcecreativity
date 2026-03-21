"""
Relative Strength IWM Trio — SLV/XLF/IWM relative strength vs SPY.

Same validated framework as SPY Rel Strength Alpha (winner) but IWM (small caps)
replaces SOXX (semiconductors). Small caps have different cycle drivers:
- Interest rate sensitivity (small caps borrow more)
- Domestic economy exposure (less international revenue)
- M&A targets (acquisition premium)

SLV + XLF + IWM represents: commodity alpha + bank earnings cycle + domestic growth.
Buy whichever has highest 10d relative strength vs SPY. Cash if none outperforming.
"""

import pandas as pd
import numpy as np

ASSETS = ["SLV", "XLF", "IWM"]

STRATEGY = {
    "name": "Rel Strength IWM Trio",
    "hypothesis": "SLV/XLF/IWM relative strength vs SPY. Small caps replace semis for domestic growth exposure.",
    "universe": ASSETS + ["SPY"],
    "entry": "Buy asset with highest 10d return vs SPY if outperforming. Cash if none beating SPY.",
    "exit": "Rotate every 3 days or -3% stop",
    "position_size": "90% of capital",
    "eccentricity": "IWM (small caps) + SLV + XLF relative strength rotation. Domestic growth + commodity + bank cycle.",
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
