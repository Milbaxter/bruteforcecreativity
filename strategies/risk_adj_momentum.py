"""
Risk-Adjusted Momentum — rotate based on return per unit of volatility.

Thesis: Raw momentum rotation buys whatever went up the most, which often catches
high-volatility assets near their peaks. Risk-adjusted momentum (5-day return / 10-day
realized vol) instead favors assets going up SMOOTHLY. This is more robust because:
1. Smooth trends are more likely to continue than violent moves
2. It naturally avoids assets in volatile/uncertain phases
3. It works in both trending and choppy markets

Universe: QQQ, XLF, SOXX, SLV, XLI, XLE, TLT
Seven diverse assets. Score each by 5d return / 10d vol. Buy the highest scorer
(must be positive return). Rotation every 3 days, -3% stop loss.
"""

import pandas as pd
import numpy as np

ASSETS = ["QQQ", "XLF", "SOXX", "SLV", "XLI", "XLE", "TLT"]

STRATEGY = {
    "name": "Risk Adjusted Momentum",
    "hypothesis": "Return/volatility ranking favors smooth trends over volatile spikes. More robust across market regimes than raw momentum.",
    "universe": ASSETS + ["SPY"],
    "entry": "Buy asset with highest 5d return / 10d vol ratio every 3 days (must have positive return)",
    "exit": "Rotate every 3 days or -3% stop loss",
    "position_size": "90% of capital",
    "eccentricity": "Risk-adjusted momentum (mini-Sharpe) instead of raw momentum for asset selection. Penalizes volatile moves that are likely to reverse.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    prices = {}
    for a in ASSETS:
        df = data_fetcher.get_prices(a, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            prices[a] = s

    if len(prices) < 4:
        return

    common = None
    for s in prices.values():
        common = s.index if common is None else common.intersection(s.index)
    if common is None or len(common) < 15:
        return
    common = common.sort_values()

    pm = pd.DataFrame({a: prices[a].loc[common] for a in prices})
    ret_5d = pm.pct_change(5)
    # 10-day realized vol (annualized)
    daily_ret = pm.pct_change()
    vol_10d = daily_ret.rolling(10).std()

    current_holding = None
    rotation_day = 0
    entry_price = None

    for i in range(12, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        rotation_day += 1

        # Stop loss check
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

        # Score each asset by risk-adjusted momentum
        best_asset = None
        best_score = 0

        for asset in prices:
            r5 = float(ret_5d[asset].iloc[i]) if pd.notna(ret_5d[asset].iloc[i]) else 0
            v10 = float(vol_10d[asset].iloc[i]) if pd.notna(vol_10d[asset].iloc[i]) else 0.01

            if r5 > 0 and v10 > 0.001:
                score = r5 / v10  # risk-adjusted momentum
                if score > best_score:
                    best_score = score
                    best_asset = asset

        target = best_asset

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
