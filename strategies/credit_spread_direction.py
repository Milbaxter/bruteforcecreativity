"""
Credit Spread Direction — HY spread CHANGE (not level) as credit regime signal.

BAMLH0A0HYM2 change over 10 days:
Narrowing (< -0.1): credit conditions improving → SOXX/XLF
Widening (> 0.1): credit stress building → GDX/SLV
Stable: pure relative strength
"""

import pandas as pd
import numpy as np

ASSETS = ["SOXX", "GDX", "SLV", "XLF"]

STRATEGY = {
    "name": "Credit Spread Direction",
    "hypothesis": "HY spread narrowing = improving credit (SOXX/XLF). Widening = stress (GDX/SLV). Direction more informative than level.",
    "universe": ASSETS + ["SPY"],
    "entry": "Growth on narrowing spreads, safety on widening, rel strength when stable.",
    "exit": "Rotate every 3 days or -3% stop",
    "position_size": "90% of capital",
    "eccentricity": "Credit spread DIRECTION (change) rather than level as regime signal. Captures shifts faster.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    hy_spread = data_fetcher.get_fred_series("BAMLH0A0HYM2", start=start_date, end=end_date)

    prices = {}
    for a in ASSETS + ["SPY"]:
        df = data_fetcher.get_prices(a, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            prices[a] = s

    if len(prices) < 5 or hy_spread.empty:
        return

    hy_spread.index = pd.to_datetime(hy_spread.index)

    common = None
    for s in prices.values():
        common = s.index if common is None else common.intersection(s.index)
    if common is None or len(common) < 15:
        return
    common = common.sort_values()

    spread_aligned = hy_spread.reindex(common, method="ffill")
    spread_change10 = spread_aligned.diff(10)

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

        sc = float(spread_change10.iloc[i]) if pd.notna(spread_change10.iloc[i]) else 0
        spy_ret = float(ret10["SPY"].iloc[i]) if pd.notna(ret10["SPY"].iloc[i]) else 0

        if sc < -0.1:
            candidates = ["SOXX", "XLF"]  # Narrowing → growth
        elif sc > 0.1:
            candidates = ["GDX", "SLV"]   # Widening → safety
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
