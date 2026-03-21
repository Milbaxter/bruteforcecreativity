"""
TLT Momentum Rotation — bond momentum direction as economic signal for sector rotation.

TLT falling (rates rising): economic strength → favor SOXX (growth cyclical).
TLT rising (rates falling): economic concern → favor GDX/SLV (real assets).
Combined with 10d relative strength vs SPY for final asset pick.
"""

import pandas as pd
import numpy as np

ASSETS = ["SOXX", "GDX", "SLV", "XLF"]

STRATEGY = {
    "name": "TLT Momentum Rotation",
    "hypothesis": "TLT 10d return direction: negative = economic strength (SOXX), positive = concern (GDX/SLV). Bond market as leading indicator.",
    "universe": ASSETS + ["TLT", "SPY"],
    "entry": "TLT falling: favor SOXX. TLT rising: favor GDX/SLV. Rel strength for final pick.",
    "exit": "Rotate every 3 days or -3% stop",
    "position_size": "90% of capital",
    "eccentricity": "Bond momentum (not level) as economic regime signal. Rising rates = growth confidence = buy growth sectors.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    prices = {}
    for a in ASSETS + ["TLT", "SPY"]:
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

        tlt_ret = float(ret10["TLT"].iloc[i]) if pd.notna(ret10["TLT"].iloc[i]) else 0
        spy_ret = float(ret10["SPY"].iloc[i]) if pd.notna(ret10["SPY"].iloc[i]) else 0

        if tlt_ret < -0.005:
            # TLT falling = rates rising = economic strength
            candidates = ["SOXX", "XLF"]
        elif tlt_ret > 0.005:
            # TLT rising = rates falling = concern
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
