"""
ISM PMI Rotation — manufacturing PMI as economic expansion/contraction signal.

MANEMP (manufacturing employment) or NAPM (ISM purchasing managers index) from FRED:
- Above 50: expansion → SOXX (cyclical growth)
- Below 50: contraction → GDX (safe haven)
- Near 50: rel strength

Using NAPMPI (ISM PMI Production Index) as the signal.
If not available, fall back to relative strength.
"""

import pandas as pd
import numpy as np

ASSETS = ["SOXX", "GDX", "SLV", "XLF"]

STRATEGY = {
    "name": "ISM PMI Rotation",
    "hypothesis": "ISM manufacturing PMI: >50 = expansion (SOXX), <50 = contraction (GDX). Classic macro signal for sector rotation.",
    "universe": ASSETS + ["SPY"],
    "entry": "SOXX on PMI > 52, GDX on PMI < 48, rel strength when 48-52.",
    "exit": "Rotate every 3 days or -3% stop",
    "position_size": "90% of capital",
    "eccentricity": "FRED manufacturing data as real-economy regime signal for sector allocation.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Try ISM PMI (NAPM) — monthly
    pmi = data_fetcher.get_fred_series("NAPM", start=start_date, end=end_date)

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

    # Align PMI to trading days
    pmi_level = 50.0  # default neutral
    if not pmi.empty:
        pmi.index = pd.to_datetime(pmi.index)
        pmi_aligned = pmi.reindex(common, method="ffill")
    else:
        pmi_aligned = pd.Series(50.0, index=common)

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

        pmi_val = float(pmi_aligned.iloc[i]) if pd.notna(pmi_aligned.iloc[i]) else 50
        spy_ret = float(ret10["SPY"].iloc[i]) if pd.notna(ret10["SPY"].iloc[i]) else 0

        if pmi_val > 52:
            target = "SOXX"  # Expansion
        elif pmi_val < 48:
            target = "GDX"   # Contraction
        else:
            # Near 50 — rel strength
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
