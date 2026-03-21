"""
Silver Tech Banks — QQQ/SLV/XLF momentum rotation across three uncorrelated assets.

Thesis: Three assets driven by completely different macroeconomic factors:
- QQQ: tech earnings, AI capex, growth sentiment
- SLV: silver (industrial demand from solar/EV + monetary hedge + speculation)
- XLF: banking profitability, interest rates, credit quality

These three rarely move together, so at any given time at least one is leading.
Momentum rotation captures whichever macro theme is currently dominant.

Silver is deliberately chosen over gold because:
1. Silver has industrial demand (solar panels, electronics) making it more cyclical
2. Silver is more volatile (bigger moves, bigger alpha opportunity)
3. Silver is less followed by institutional investors (less crowded)

5-day momentum lookback, 3-day rotation, -3% stop loss.
"""

import pandas as pd
import numpy as np

ASSETS = ["QQQ", "SLV", "XLF"]

STRATEGY = {
    "name": "Silver Tech Banks",
    "hypothesis": "QQQ/SLV/XLF are driven by different macro factors (tech, commodities, rates). Rotate into 5-day momentum leader every 3 days.",
    "universe": ASSETS + ["SPY"],
    "entry": "Buy 5-day momentum leader from QQQ/SLV/XLF every 3 days",
    "exit": "Rotate every 3 days or -3% stop loss",
    "position_size": "90% of capital",
    "eccentricity": "Silver (not gold) as commodity component — more volatile, industrial demand driven. Combined with tech and banks for maximum diversification of drivers.",
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
    if common is None or len(common) < 10:
        return
    common = common.sort_values()

    pm = pd.DataFrame({a: prices[a].loc[common] for a in prices})
    ret5 = pm.pct_change(5)

    current_holding = None
    rotation_day = 0
    entry_price = None

    for i in range(7, len(common)):
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

        # Find momentum leader
        row = ret5.iloc[i].dropna()
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
