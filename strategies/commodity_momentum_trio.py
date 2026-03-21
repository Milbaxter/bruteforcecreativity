"""
Commodity Momentum Trio — USO/SLV/UNG pure commodity rotation.

Thesis: Three commodity ETFs driven by completely different fundamental factors:
- USO (oil): geopolitics, OPEC decisions, global growth, weather
- SLV (silver): industrial demand (solar/EV), inflation expectations, gold sympathy
- UNG (natural gas): weather, storage levels, LNG exports, heating/cooling demand

These three commodities are nearly uncorrelated. When one catches a catalyst, momentum
persists for days because physical commodity markets adjust slowly.

The key edge: NO equities, NO bonds. This is a pure alternative asset rotation that
generates returns independent of the stock market. If everything else in the portfolio
is equity-correlated, this adds genuine diversification of alpha.

7-day momentum lookback, 3-day rotation, only enter if leader has positive return.
"""

import pandas as pd
import numpy as np

COMMODITIES = ["USO", "SLV", "UNG"]

STRATEGY = {
    "name": "Commodity Momentum Trio",
    "hypothesis": "USO/SLV/UNG are driven by different factors (geopolitics, industrial demand, weather). Rotate into 7-day momentum leader. Pure commodity alpha.",
    "universe": COMMODITIES + ["SPY"],
    "entry": "Buy 7-day momentum leader from USO/SLV/UNG every 3 days if return > 0",
    "exit": "Rotate every 3 days. Cash if all negative.",
    "position_size": "90% of capital",
    "eccentricity": "Pure commodity rotation with no equity/bond exposure. Three uncorrelated commodities provide market-independent returns.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    prices = {}
    for c in COMMODITIES:
        df = data_fetcher.get_prices(c, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            prices[c] = s

    if len(prices) < 3:
        return

    common = None
    for s in prices.values():
        common = s.index if common is None else common.intersection(s.index)
    if common is None or len(common) < 12:
        return
    common = common.sort_values()

    pm = pd.DataFrame({c: prices[c].loc[common] for c in prices})
    ret7 = pm.pct_change(7)

    current_holding = None
    rotation_day = 0

    for i in range(9, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        rotation_day += 1

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
                portfolio.buy(target, dollars=portfolio.cash * 0.9, date=date_str)
            current_holding = target
            rotation_day = 0

    if current_holding:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(current_holding, all_shares=True, date=last_date)
