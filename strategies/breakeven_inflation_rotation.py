"""
Breakeven Inflation Rotation — 5Y breakeven inflation rate as inflation expectations signal.

T5YIE from FRED: market-implied inflation expectations.
- Rising (7d change > 0.03): inflation concerns → SLV/GDX (real assets)
- Falling (7d change < -0.03): disinflation → SOXX (growth benefits)
- Stable: relative strength among all 4
"""

import pandas as pd
import numpy as np

ASSETS = ["SOXX", "GDX", "SLV", "XLF"]

STRATEGY = {
    "name": "Breakeven Inflation Rotation",
    "hypothesis": "5Y breakeven inflation: rising = commodities (SLV/GDX), falling = growth (SOXX), stable = rel strength.",
    "universe": ASSETS + ["SPY"],
    "entry": "SLV/GDX on rising inflation expectations, SOXX on falling, rel strength when stable.",
    "exit": "Rotate every 3 days or -3% stop",
    "position_size": "90% of capital",
    "eccentricity": "Market-implied inflation expectations (TIPS breakevens) as sector allocation signal.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    bei = data_fetcher.get_fred_series("T5YIE", start=start_date, end=end_date)

    prices = {}
    for a in ASSETS + ["SPY"]:
        df = data_fetcher.get_prices(a, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            prices[a] = s

    if len(prices) < 5 or bei.empty:
        return

    bei.index = pd.to_datetime(bei.index)

    common = None
    for s in prices.values():
        common = s.index if common is None else common.intersection(s.index)
    if common is None or len(common) < 15:
        return
    common = common.sort_values()

    bei_aligned = bei.reindex(common, method="ffill")
    bei_change7 = bei_aligned.diff(7)

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

        bei_chg = float(bei_change7.iloc[i]) if pd.notna(bei_change7.iloc[i]) else 0
        spy_ret = float(ret10["SPY"].iloc[i]) if pd.notna(ret10["SPY"].iloc[i]) else 0

        if bei_chg > 0.03:
            # Rising inflation expectations → real assets
            slv_alpha = float(ret10["SLV"].iloc[i]) - spy_ret if pd.notna(ret10["SLV"].iloc[i]) else 0
            gdx_alpha = float(ret10["GDX"].iloc[i]) - spy_ret if pd.notna(ret10["GDX"].iloc[i]) else 0
            target = "SLV" if slv_alpha > gdx_alpha else "GDX"
        elif bei_chg < -0.03:
            target = "SOXX"  # Disinflation → growth
        else:
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
