"""
M2 Liquidity Rotation — FRED M2 money supply direction as liquidity regime signal.

When M2 is growing (3-month change positive): liquidity expanding → favor SOXX/XLF.
When M2 is contracting: liquidity tightening → favor SLV/GDX (real assets).
Combine with 10-day relative strength vs SPY for asset selection.
"""

import pandas as pd
import numpy as np

ASSETS = ["SLV", "XLF", "SOXX", "GDX"]

STRATEGY = {
    "name": "M2 Liquidity Rotation",
    "hypothesis": "M2 money supply growth = favor growth assets (SOXX/XLF). M2 contraction = favor commodities (SLV/GDX). Combined with relative strength.",
    "universe": ASSETS + ["SPY"],
    "entry": "M2 growing: rel strength among SOXX/XLF. M2 contracting: rel strength among SLV/GDX.",
    "exit": "Rotate every 3 days or -3% stop",
    "position_size": "90% of capital",
    "eccentricity": "FRED M2 money supply as liquidity regime filter for sector relative strength rotation.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # M2 money supply from FRED
    m2 = data_fetcher.get_fred_series("M2SL", start=start_date, end=end_date)

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
    if common is None or len(common) < 15:
        return
    common = common.sort_values()

    pm = pd.DataFrame({a: prices[a].loc[common] for a in prices})
    ret10 = pm.pct_change(10)

    # M2 direction: positive = growing
    m2_growing = True  # default to growing if data unavailable
    if not m2.empty:
        m2.index = pd.to_datetime(m2.index)
        # Monthly data — check if recent values are trending up
        if len(m2) >= 3:
            m2_growing = float(m2.iloc[-1]) > float(m2.iloc[-3])

    # Set candidate pools based on M2
    if m2_growing:
        primary = ["SOXX", "XLF"]
        secondary = ["SLV", "GDX"]
    else:
        primary = ["SLV", "GDX"]
        secondary = ["SOXX", "XLF"]

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

        # Check primary pool first, then secondary
        best_asset = None
        best_alpha = 0

        for asset in primary:
            asset_ret = float(ret10[asset].iloc[i]) if pd.notna(ret10[asset].iloc[i]) else 0
            alpha = asset_ret - spy_ret
            if alpha > best_alpha:
                best_alpha = alpha
                best_asset = asset

        if not best_asset:
            # No primary outperformer — check secondary
            for asset in secondary:
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
