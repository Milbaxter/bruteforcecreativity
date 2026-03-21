"""
Acceleration Momentum — rotate into the asset with accelerating (not just positive) momentum.

Thesis: Plain momentum (5d or 10d return) is noisy and well-arbitraged. But ACCELERATING
momentum — when the short-term return exceeds the longer-term return — signals a trend
that's gaining strength. This second derivative of price is much harder to fake and
less crowded because most momentum strategies ignore it.

Score each asset: acceleration = 5d return - 10d return. Positive acceleration means
the trend is getting STRONGER. Buy the asset with the highest positive acceleration
every 3 days. If no asset is accelerating, go to cash.

Universe: QQQ (US tech), EEM (emerging markets), TLT (bonds), BITO (crypto).
Four maximally different asset classes to ensure diverse catalyst exposure.
"""

import pandas as pd
import numpy as np

ASSETS = ["QQQ", "EEM", "TLT", "BITO"]

STRATEGY = {
    "name": "Acceleration Momentum",
    "hypothesis": "The derivative of momentum (acceleration = 5d ret minus 10d ret) is a stronger signal than raw momentum. Rotate into the most accelerating asset every 3 days.",
    "universe": ASSETS + ["SPY"],
    "entry": "Buy asset with highest positive acceleration (5d_ret - 10d_ret > 0). Cash if no acceleration.",
    "exit": "Rotate every 3 days",
    "position_size": "90% of capital",
    "eccentricity": "Second derivative of price (acceleration) as primary signal instead of first derivative (momentum). Less crowded, harder to arbitrage.",
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
    if common is None or len(common) < 15:
        return
    common = common.sort_values()

    pm = pd.DataFrame({a: prices[a].loc[common] for a in prices})

    ret_5d = pm.pct_change(5)
    ret_10d = pm.pct_change(10)
    acceleration = ret_5d - ret_10d  # positive = trend strengthening

    current_holding = None
    rotation_day = 0

    for i in range(12, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        rotation_day += 1

        if rotation_day < 3 and current_holding is not None:
            continue

        # Find asset with highest acceleration
        row = acceleration.iloc[i].dropna()
        if row.empty:
            continue

        # Only consider positive acceleration AND positive 5d return
        ret5_row = ret_5d.iloc[i].dropna()
        candidates = {}
        for asset in row.index:
            accel = float(row[asset])
            r5 = float(ret5_row[asset]) if asset in ret5_row.index else 0
            if accel > 0 and r5 > 0:
                candidates[asset] = accel

        if candidates:
            target = max(candidates, key=candidates.get)
        else:
            target = None

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
