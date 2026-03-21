"""
Crypto Fear Homebuilders — crypto fear regime for SLV/XHB/QQQ rotation.

Homebuilders (XHB) benefit from rate normalization and housing demand.
- Fear (< 25): SLV (commodity safe haven)
- Moderate (25-55): XHB (homebuilders, rate-sensitive, demographic tailwind)
- Greed (> 55): QQQ (tech risk-on)
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Crypto Fear Homebuilders",
    "hypothesis": "Crypto fear regime for SLV (fear) / XHB (moderate) / QQQ (greed). Homebuilders as rate-sensitive moderate allocation.",
    "universe": ["QQQ", "SLV", "XHB", "SPY"],
    "entry": "SLV when crypto fear < 25, XHB when 25-55, QQQ when > 55.",
    "exit": "Rotate every 3 days",
    "position_size": "90% of capital",
    "eccentricity": "Homebuilders (XHB) as moderate allocation — rate sensitive + housing demographic cycle.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    crypto_fg = data_fetcher.get_crypto_fear_greed(days=400)
    prices = {}
    for a in ["QQQ", "SLV", "XHB"]:
        df = data_fetcher.get_prices(a, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            prices[a] = s

    if len(prices) < 3 or crypto_fg.empty:
        return

    crypto_fg.index = pd.to_datetime(crypto_fg.index)
    common = None
    for s in prices.values():
        common = s.index if common is None else common.intersection(s.index)
    if common is None or len(common) < 10:
        return
    common = common.sort_values()

    fg_aligned = crypto_fg.reindex(common, method="ffill")
    pm = pd.DataFrame({a: prices[a].loc[common] for a in prices})
    ret5 = pm.pct_change(5)

    current_holding = None
    rotation_day = 0

    for i in range(7, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        rotation_day += 1
        if rotation_day < 3 and current_holding is not None:
            continue

        fg = float(fg_aligned.iloc[i]) if pd.notna(fg_aligned.iloc[i]) else 50

        if fg < 25:
            target = "SLV"
        elif fg > 55:
            target = "QQQ"
        else:
            row = ret5.iloc[i].dropna()
            if not row.empty:
                best = row.idxmax()
                target = best if float(row[best]) > 0 else "XHB"
            else:
                target = "XHB"

        if target != current_holding:
            if current_holding:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
            portfolio.buy(target, dollars=portfolio.cash * 0.9, date=date_str)
            current_holding = target
            rotation_day = 0

    if current_holding:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(current_holding, all_shares=True, date=last_date)
