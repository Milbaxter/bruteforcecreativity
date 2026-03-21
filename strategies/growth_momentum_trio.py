"""
Growth Momentum Trio — rotate among QQQ, SOXX, BITO based on 5-day momentum.

Thesis: In a secular growth environment, the question isn't "growth vs value" — it's
WHICH growth theme is hottest right now. Tech (QQQ), semiconductors (SOXX), and crypto
(BITO) are driven by different-but-related catalysts:
- QQQ: broad tech (FAANG, AI), driven by earnings and AI narrative
- SOXX: hardware cycle (chips, data centers), driven by capex and supply chain
- BITO: crypto adoption, driven by ETF flows, halving cycle, risk appetite

These three assets are positively correlated but NOT identical. When one leads, it
tends to continue for days as flows are sticky. Momentum rotation captures this.

Rotation every 3 days into the 5-day momentum leader. -4% stop loss on any position.
Only buy if leader has positive 5-day return.
"""

import pandas as pd
import numpy as np

ASSETS = ["QQQ", "SOXX", "BITO"]

STRATEGY = {
    "name": "Growth Momentum Trio",
    "hypothesis": "Rotate among QQQ/SOXX/BITO every 3 days into the 5-day momentum leader. Three different growth themes with sticky flows.",
    "universe": ASSETS + ["SPY"],
    "entry": "Buy 5-day momentum leader from QQQ/SOXX/BITO every 3 days if return > 0",
    "exit": "Rotate every 3 days or -4% stop loss",
    "position_size": "90% of capital",
    "eccentricity": "Three high-beta growth assets from different themes (broad tech, semis, crypto). Nobody combines these three for momentum rotation.",
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
            if pnl_pct <= -0.04:
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
