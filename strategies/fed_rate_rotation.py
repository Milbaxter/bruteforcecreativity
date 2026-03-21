"""
Fed Rate Rotation — Fed funds rate direction as monetary policy regime signal.

DFF (daily federal funds rate) from FRED:
- Rate falling (30d change < -0.1): easing cycle → SOXX (growth benefits)
- Rate rising (30d change > 0.1): tightening → GDX (safe haven)
- Rate stable: relative strength among SLV/XLF/SOXX/GDX
"""

import pandas as pd
import numpy as np

ASSETS = ["SOXX", "GDX", "SLV", "XLF"]

STRATEGY = {
    "name": "Fed Rate Rotation",
    "hypothesis": "Fed funds rate direction: falling = growth (SOXX), rising = safety (GDX), stable = rel strength. Monetary policy drives asset returns.",
    "universe": ASSETS + ["SPY"],
    "entry": "SOXX on rate cuts, GDX on hikes, rel strength when stable.",
    "exit": "Rotate every 3 days or -3% stop",
    "position_size": "90% of capital",
    "eccentricity": "FRED fed funds rate as monetary policy regime signal for sector rotation.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    dff = data_fetcher.get_fred_series("DFF", start=start_date, end=end_date)

    prices = {}
    for a in ASSETS + ["SPY"]:
        df = data_fetcher.get_prices(a, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            prices[a] = s

    if len(prices) < 5 or dff.empty:
        return

    dff.index = pd.to_datetime(dff.index)

    common = None
    for s in prices.values():
        common = s.index if common is None else common.intersection(s.index)
    if common is None or len(common) < 35:
        return
    common = common.sort_values()

    dff_aligned = dff.reindex(common, method="ffill")
    dff_change30 = dff_aligned.diff(30)

    pm = pd.DataFrame({a: prices[a].loc[common] for a in prices})
    ret10 = pm.pct_change(10)

    current_holding = None
    rotation_day = 0
    entry_price = None

    for i in range(35, len(common)):
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

        rate_chg = float(dff_change30.iloc[i]) if pd.notna(dff_change30.iloc[i]) else 0
        spy_ret = float(ret10["SPY"].iloc[i]) if pd.notna(ret10["SPY"].iloc[i]) else 0

        if rate_chg < -0.1:
            target = "SOXX"  # Easing → growth
        elif rate_chg > 0.1:
            target = "GDX"   # Tightening → safe haven
        else:
            # Stable — rel strength
            best = None
            best_alpha = 0
            for a in ASSETS:
                ar = float(ret10[a].iloc[i]) if pd.notna(ret10[a].iloc[i]) else 0
                alpha = ar - spy_ret
                if alpha > best_alpha:
                    best_alpha = alpha
                    best = a
            target = best if best else "XLF"

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
