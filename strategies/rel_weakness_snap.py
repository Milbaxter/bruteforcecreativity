"""
Relative Weakness Snap — buy the asset MOST underperforming SPY for mean reversion.

Thesis: The INVERSE of relative strength — instead of buying the leader, buy the
laggard. When one of SLV/XLF/SOXX/GDX underperforms SPY the most over 10 days,
it's likely oversold and due for a snap-back. The mean reversion in relative
performance is a well-documented effect.

Only buy if: the underperformance is significant (> 3% worse than SPY) AND the asset
is above its 50-day MA (long-term trend intact, just short-term weakness).

Hold 5 days for the mean reversion.
"""

import pandas as pd
import numpy as np

ASSETS = ["SLV", "XLF", "SOXX", "GDX"]

STRATEGY = {
    "name": "Rel Weakness Snap",
    "hypothesis": "Buy the asset most underperforming SPY (> 3% gap) if above 50d MA. Relative mean reversion within a trend.",
    "universe": ASSETS + ["SPY"],
    "entry": "Buy asset with lowest 10d return vs SPY if gap > 3% AND above 50d MA.",
    "exit": "Sell after 5 days or +4%/-2% stop",
    "position_size": "85% of capital per trade",
    "eccentricity": "Relative WEAKNESS (not strength) as entry signal. Contrarian within established trends.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    prices = {}
    for a in ASSETS + ["SPY"]:
        df = data_fetcher.get_prices(a, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            prices[a] = s

    if len(prices) < 5:
        return

    common = None
    for s in prices.values():
        common = s.index if common is None else common.intersection(s.index)
    if common is None or len(common) < 55:
        return
    common = common.sort_values()

    pm = pd.DataFrame({a: prices[a].loc[common] for a in prices})
    ret10 = pm.pct_change(10)
    ma50 = pm.rolling(50).mean()

    in_trade = False
    trade_ticker = None
    entry_price = None
    days_held = 0

    for i in range(55, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")

        if in_trade:
            days_held += 1
            curr = float(pm[trade_ticker].iloc[i])
            pnl_pct = (curr - entry_price) / entry_price

            if days_held >= 5 or pnl_pct >= 0.04 or pnl_pct <= -0.02:
                portfolio.sell(trade_ticker, all_shares=True, date=date_str)
                in_trade = False
                trade_ticker = None
                entry_price = None
                days_held = 0

        elif not in_trade:
            spy_ret = float(ret10["SPY"].iloc[i]) if pd.notna(ret10["SPY"].iloc[i]) else 0

            worst_asset = None
            worst_alpha = 0

            for asset in ASSETS:
                asset_ret = float(ret10[asset].iloc[i]) if pd.notna(ret10[asset].iloc[i]) else 0
                price = float(pm[asset].iloc[i])
                ma = float(ma50[asset].iloc[i]) if pd.notna(ma50[asset].iloc[i]) else price

                alpha = asset_ret - spy_ret
                # Must be significantly underperforming AND above long-term trend
                if alpha < -0.03 and price > ma and alpha < worst_alpha:
                    worst_alpha = alpha
                    worst_asset = asset

            if worst_asset:
                price = float(pm[worst_asset].iloc[i])
                result = portfolio.buy(worst_asset, dollars=portfolio.cash * 0.85, date=date_str)
                if result:
                    in_trade = True
                    trade_ticker = worst_asset
                    entry_price = price
                    days_held = 0

    if in_trade:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(trade_ticker, all_shares=True, date=last_date)
