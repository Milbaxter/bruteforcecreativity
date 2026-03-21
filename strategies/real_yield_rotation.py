"""
Real Yield Rotation — 10Y TIPS real yield direction as regime signal.

DFII10 (10Y TIPS real yield) from FRED:
- Rising real yields: discount rate rising, hurts long-duration growth → GDX/SLV
- Falling real yields: easier financial conditions → SOXX (growth)
- Stable: rel strength among all

7-day direction of real yields determines allocation preference.
"""

import pandas as pd
import numpy as np

ASSETS = ["SOXX", "GDX", "SLV", "XLF"]

STRATEGY = {
    "name": "Real Yield Rotation",
    "hypothesis": "10Y real yield direction: falling = growth (SOXX), rising = real assets (GDX/SLV). Stable = rel strength.",
    "universe": ASSETS + ["SPY"],
    "entry": "SOXX when real yields falling, GDX/SLV when rising, rel strength when stable.",
    "exit": "Rotate every 3 days or -3% stop",
    "position_size": "90% of capital",
    "eccentricity": "TIPS real yield as regime signal. Real yields directly impact asset class valuations — a fundamental driver.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    real_yield = data_fetcher.get_fred_series("DFII10", start=start_date, end=end_date)

    prices = {}
    for a in ASSETS + ["SPY"]:
        df = data_fetcher.get_prices(a, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            prices[a] = s

    if len(prices) < 5 or real_yield.empty:
        return

    real_yield.index = pd.to_datetime(real_yield.index)

    common = None
    for s in prices.values():
        common = s.index if common is None else common.intersection(s.index)
    if common is None or len(common) < 15:
        return
    common = common.sort_values()

    ry_aligned = real_yield.reindex(common, method="ffill")
    ry_change7 = ry_aligned.diff(7)

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

        ry_chg = float(ry_change7.iloc[i]) if pd.notna(ry_change7.iloc[i]) else 0
        spy_ret = float(ret10["SPY"].iloc[i]) if pd.notna(ret10["SPY"].iloc[i]) else 0

        if ry_chg < -0.05:
            # Real yields falling → growth
            target = "SOXX"
        elif ry_chg > 0.05:
            # Real yields rising → real assets
            gdx_alpha = float(ret10["GDX"].iloc[i]) - spy_ret if pd.notna(ret10["GDX"].iloc[i]) else 0
            slv_alpha = float(ret10["SLV"].iloc[i]) - spy_ret if pd.notna(ret10["SLV"].iloc[i]) else 0
            target = "GDX" if gdx_alpha > slv_alpha else "SLV"
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
