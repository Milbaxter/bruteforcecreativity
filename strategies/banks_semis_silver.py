"""
Banks Semis Silver — XLF/SOXX/SLV momentum rotation across three macro themes.

Thesis: Three sector ETFs driven by completely different macro forces:
- XLF (banks): interest rate direction, credit conditions, regulatory environment
- SOXX (semis): technology capex cycle, AI investment, chip demand/supply
- SLV (silver): industrial demand (solar/EV), inflation expectations, gold sympathy

At any point, one of these macro themes is dominant. Momentum rotation captures the
shift between themes. 7-day lookback for more stable signals, 3-day rotation.

Deliberately excludes QQQ to find alpha OUTSIDE of broad tech. Each of these sectors
can outperform QQQ for weeks at a time when their specific catalyst is active.
"""

import pandas as pd
import numpy as np

ASSETS = ["XLF", "SOXX", "SLV"]

STRATEGY = {
    "name": "Banks Semis Silver",
    "hypothesis": "XLF/SOXX/SLV rotate based on which macro theme (rates, tech cycle, commodities) is dominant. 7-day momentum, 3-day rotation.",
    "universe": ASSETS + ["SPY"],
    "entry": "Buy 7-day momentum leader from XLF/SOXX/SLV every 3 days if return > 0",
    "exit": "Rotate every 3 days or -3% stop loss",
    "position_size": "90% of capital",
    "eccentricity": "Non-QQQ sector rotation across three fundamentally different macro drivers. Banks, semis, and silver never move together.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    prices = {}
    for a in ASSETS:
        df = data_fetcher.get_prices(a, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            prices[a] = s

    if len(prices) < 3:
        return

    common = None
    for s in prices.values():
        common = s.index if common is None else common.intersection(s.index)
    if common is None or len(common) < 12:
        return
    common = common.sort_values()

    pm = pd.DataFrame({a: prices[a].loc[common] for a in prices})
    ret7 = pm.pct_change(7)

    current_holding = None
    rotation_day = 0
    entry_price = None

    for i in range(9, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        rotation_day += 1

        # Check stop loss
        if current_holding and entry_price:
            curr_price = float(pm[current_holding].iloc[i])
            pnl_pct = (curr_price - entry_price) / entry_price
            if pnl_pct <= -0.03:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
                current_holding = None
                entry_price = None
                rotation_day = 0
                continue

        if rotation_day < 3 and current_holding is not None:
            continue

        row = ret7.iloc[i].dropna()
        if row.empty:
            continue

        best = row.idxmax()
        best_ret = float(row[best])
        target = best if best_ret > 0 else None

        if target != current_holding:
            if current_holding:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
            if target:
                result = portfolio.buy(target, dollars=portfolio.cash * 0.9, date=date_str)
                if result:
                    entry_price = float(pm[target].iloc[i])
                else:
                    target = None
            current_holding = target
            rotation_day = 0

    if current_holding:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(current_holding, all_shares=True, date=last_date)
