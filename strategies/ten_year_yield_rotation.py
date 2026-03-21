"""
10Y Yield Direction Rotation — direct 10Y yield change as rate regime signal.

DGS10 from FRED: 10-Year Treasury yield.
Yield rising (10d change > 0.1): growth confidence → SOXX/XLF
Yield falling (10d change < -0.1): concern/easing → GDX/SLV
Stable: pure relative strength
"""

import pandas as pd
import numpy as np

ASSETS = ["SOXX", "GDX", "SLV", "XLF"]

STRATEGY = {
    "name": "10Y Yield Direction",
    "hypothesis": "10Y yield rising = growth (SOXX/XLF), falling = safety (GDX/SLV), stable = rel strength.",
    "universe": ASSETS + ["SPY"],
    "entry": "Growth on rising yields, safety on falling, rel strength when stable.",
    "exit": "Rotate every 3 days or -3% stop",
    "position_size": "90% of capital",
    "eccentricity": "Direct 10Y yield direction (not spread) as simplest possible rate regime signal.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    dgs10 = data_fetcher.get_fred_series("DGS10", start=start_date, end=end_date)

    prices = {}
    for a in ASSETS + ["SPY"]:
        df = data_fetcher.get_prices(a, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            prices[a] = s

    if len(prices) < 5 or dgs10.empty:
        return

    dgs10.index = pd.to_datetime(dgs10.index)

    common = None
    for s in prices.values():
        common = s.index if common is None else common.intersection(s.index)
    if common is None or len(common) < 15:
        return
    common = common.sort_values()

    yield_aligned = dgs10.reindex(common, method="ffill")
    yield_change10 = yield_aligned.diff(10)

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

        yc = float(yield_change10.iloc[i]) if pd.notna(yield_change10.iloc[i]) else 0
        spy_ret = float(ret10["SPY"].iloc[i]) if pd.notna(ret10["SPY"].iloc[i]) else 0

        if yc > 0.1:
            candidates = ["SOXX", "XLF"]
        elif yc < -0.1:
            candidates = ["GDX", "SLV"]
        else:
            candidates = ASSETS

        best = None
        best_alpha = 0
        for a in candidates:
            ar = float(ret10[a].iloc[i]) if pd.notna(ret10[a].iloc[i]) else 0
            alpha = ar - spy_ret
            if alpha > best_alpha:
                best_alpha = alpha
                best = a

        if not best:
            for a in ASSETS:
                ar = float(ret10[a].iloc[i]) if pd.notna(ret10[a].iloc[i]) else 0
                alpha = ar - spy_ret
                if alpha > best_alpha:
                    best_alpha = alpha
                    best = a

        target = best
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
