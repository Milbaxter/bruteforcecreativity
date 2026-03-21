"""
Dollar Rel Strength — dollar direction narrows candidates for relative strength rotation.

Dollar weakening (UUP 10d < -0.5%): favor commodities (SLV, GDX) — dollar-denominated commodities benefit.
Dollar strengthening (UUP 10d > 0.5%): favor growth (SOXX) — strong dollar = US exceptionalism.
Neutral: all 4 assets by relative strength.
"""

import pandas as pd
import numpy as np

ASSETS = ["SOXX", "GDX", "SLV", "XLF"]

STRATEGY = {
    "name": "Dollar Rel Strength",
    "hypothesis": "Dollar direction filters candidates: weak USD = SLV/GDX, strong USD = SOXX. Rel strength for final pick.",
    "universe": ASSETS + ["UUP", "SPY"],
    "entry": "Weak dollar: rel strength among SLV/GDX. Strong dollar: SOXX. Neutral: all 4.",
    "exit": "Rotate every 3 days or -3% stop",
    "position_size": "90% of capital",
    "eccentricity": "Dollar direction as gating filter for commodity vs growth candidates in relative strength rotation.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    prices = {}
    for a in ASSETS + ["UUP", "SPY"]:
        df = data_fetcher.get_prices(a, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            prices[a] = s

    if len(prices) < 6:
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

        uup_ret = float(ret10["UUP"].iloc[i]) if pd.notna(ret10["UUP"].iloc[i]) else 0
        spy_ret = float(ret10["SPY"].iloc[i]) if pd.notna(ret10["SPY"].iloc[i]) else 0

        if uup_ret < -0.005:
            candidates = ["SLV", "GDX"]  # Weak dollar → commodities
        elif uup_ret > 0.005:
            candidates = ["SOXX", "XLF"]  # Strong dollar → growth/banks
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
