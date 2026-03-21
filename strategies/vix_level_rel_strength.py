"""
VIX Level Rel Strength — VIX level as regime filter for sector relative strength.

VIX < 18: calm → favor SOXX (growth)
VIX > 25: stressed → favor GDX (safety)
18-25: normal → pure relative strength among all 4
"""

import pandas as pd
import numpy as np

ASSETS = ["SOXX", "GDX", "SLV", "XLF"]

STRATEGY = {
    "name": "VIX Level Rel Strength",
    "hypothesis": "VIX level filters: <18 = SOXX, >25 = GDX, normal = rel strength. Simple but persistent.",
    "universe": ASSETS + ["SPY"],
    "entry": "SOXX on low VIX, GDX on high VIX, rel strength when normal.",
    "exit": "Rotate every 3 days or -3% stop",
    "position_size": "90% of capital",
    "eccentricity": "VIX level as simple regime filter for sector relative strength. Persistence of VIX mean-reversion creates a robust signal.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    vix = data_fetcher.get_vix(start=start_date, end=end_date)

    prices = {}
    for a in ASSETS + ["SPY"]:
        df = data_fetcher.get_prices(a, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            prices[a] = s

    if len(prices) < 5 or vix.empty:
        return

    vix.index = pd.to_datetime(vix.index)

    common = None
    for s in prices.values():
        common = s.index if common is None else common.intersection(s.index)
    common = common.intersection(vix.index)
    if common is None or len(common) < 15:
        return
    common = common.sort_values()

    pm = pd.DataFrame({a: prices[a].loc[common] for a in prices})
    ret10 = pm.pct_change(10)
    vix_c = vix.loc[common]

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

        v = float(vix_c.iloc[i])
        spy_ret = float(ret10["SPY"].iloc[i]) if pd.notna(ret10["SPY"].iloc[i]) else 0

        if v < 18:
            # Calm → growth with rel strength check
            soxx_alpha = float(ret10["SOXX"].iloc[i]) - spy_ret if pd.notna(ret10["SOXX"].iloc[i]) else 0
            target = "SOXX" if soxx_alpha > 0 else None
        elif v > 25:
            # Stressed → safety with rel strength check
            gdx_alpha = float(ret10["GDX"].iloc[i]) - spy_ret if pd.notna(ret10["GDX"].iloc[i]) else 0
            target = "GDX" if gdx_alpha > 0 else "SLV"
        else:
            target = None

        if target is None:
            # Normal or no strong signal → pure rel strength
            best = None
            best_alpha = 0
            for a in ASSETS:
                ar = float(ret10[a].iloc[i]) if pd.notna(ret10[a].iloc[i]) else 0
                alpha = ar - spy_ret
                if alpha > best_alpha:
                    best_alpha = alpha
                    best = a
            target = best

        if target and target != current_holding:
            if current_holding:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
            result = portfolio.buy(target, dollars=portfolio.cash * 0.9, date=date_str)
            if result:
                entry_price = float(pm[target].iloc[i])
            current_holding = target
            rotation_day = 0

    if current_holding:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(current_holding, all_shares=True, date=last_date)
