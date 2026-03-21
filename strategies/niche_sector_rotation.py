"""
Niche Sector Momentum Rotation — rotate among 4 eccentric sector ETFs every 3 days.

Thesis: Niche sector ETFs (airlines, solar, rare earths, crypto stocks) are driven by
completely different catalysts and are too small for institutional rotation strategies.
When one of these sectors catches a catalyst (oil prices for JETS, solar policy for TAN,
EV demand for REMX, crypto rally for BITQ), the momentum tends to persist for days
because the sectors are under-covered and retail flows are sticky.

By rotating into the 5-day momentum leader every 3 days, we capture sector-specific
momentum while avoiding getting stuck in any one sector's downturn.

Universe: JETS (airlines), TAN (solar), REMX (rare earths/metals), BITQ (crypto equities)
Only buy if the leader has positive 5-day return. Otherwise cash.
"""

import pandas as pd
import numpy as np

NICHES = ["JETS", "TAN", "REMX", "BITQ"]

STRATEGY = {
    "name": "Niche Sector Rotation",
    "hypothesis": "Niche sector ETFs have persistent momentum when catalysts hit. Rotate into the 5-day leader every 3 days across airlines/solar/rare earths/crypto stocks.",
    "universe": NICHES + ["SPY"],
    "entry": "Buy 5-day momentum leader from JETS/TAN/REMX/BITQ every 3 days if leader return > 0",
    "exit": "Rotate every 3 days. Cash if all negative.",
    "position_size": "90% of capital",
    "eccentricity": "Combines 4 unrelated niche sectors no institution would put together. Each too small for big funds. Catalyst-driven momentum in under-covered spaces.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    prices = {}
    for n in NICHES:
        df = data_fetcher.get_prices(n, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            prices[n] = s

    if len(prices) < 3:
        return

    # Common dates
    common = None
    for s in prices.values():
        common = s.index if common is None else common.intersection(s.index)
    if common is None or len(common) < 10:
        return
    common = common.sort_values()

    pm = pd.DataFrame({n: prices[n].loc[common] for n in prices})
    ret5 = pm.pct_change(5)

    current_holding = None
    rotation_day = 0

    for i in range(7, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        rotation_day += 1

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
                portfolio.buy(target, dollars=portfolio.cash * 0.9, date=date_str)
            current_holding = target
            rotation_day = 0

    if current_holding:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(current_holding, all_shares=True, date=last_date)
