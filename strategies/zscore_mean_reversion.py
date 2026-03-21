"""
Z-Score Mean Reversion — buy the most statistically oversold asset across 5 ETFs.

Thesis: Instead of using raw returns (which aren't comparable across assets with different
volatilities), use z-scores (returns normalized by their own volatility). The asset with
the most negative z-score has the biggest pullback RELATIVE TO ITS OWN NORMAL BEHAVIOR.

This is a pure statistical mean-reversion play:
- Compute 5-day return z-score = (5d return - 60d mean return) / (60d std of returns)
- Buy the asset with z-score < -1.5 (1.5+ standard deviations below normal)
- Only if price > 20-day MA (trend not broken — just a pullback, not a reversal)
- Among qualifiers, buy the one with the most negative z-score

Hold 5 days for reversion to the mean.

Universe: QQQ, SOXX, XLF, SLV, IWM — five diverse ETFs where each has different
volatility profiles that the z-score normalization handles.
"""

import pandas as pd
import numpy as np

ASSETS = ["QQQ", "SOXX", "XLF", "SLV", "IWM"]

STRATEGY = {
    "name": "Z-Score Mean Reversion",
    "hypothesis": "Buy the asset with the most negative z-score (deepest relative pullback) from 5 ETFs if still above 20d MA. Statistical mean-reversion with trend guard.",
    "universe": ASSETS + ["SPY"],
    "entry": "Buy asset with 5d return z-score < -1.5 AND above 20d MA. Most depressed wins.",
    "exit": "Sell after 5 days or +3%/-2% stop",
    "position_size": "85% of capital per trade",
    "eccentricity": "Z-score normalization makes cross-asset pullback comparison statistically rigorous. Not just 'biggest drop' but 'most abnormal drop for this specific asset'.",
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
    if common is None or len(common) < 65:
        return
    common = common.sort_values()

    pm = pd.DataFrame({a: prices[a].loc[common] for a in prices})
    ret5 = pm.pct_change(5)
    ma20 = pm.rolling(20).mean()

    # Rolling 60-day mean and std of 5-day returns
    ret5_mean = ret5.rolling(60).mean()
    ret5_std = ret5.rolling(60).std()
    z_score = (ret5 - ret5_mean) / ret5_std

    in_trade = False
    trade_ticker = None
    entry_price = None
    days_held = 0

    for i in range(65, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")

        if in_trade:
            days_held += 1
            curr = float(pm[trade_ticker].iloc[i])
            pnl_pct = (curr - entry_price) / entry_price

            if days_held >= 5 or pnl_pct >= 0.03 or pnl_pct <= -0.02:
                portfolio.sell(trade_ticker, all_shares=True, date=date_str)
                in_trade = False
                trade_ticker = None
                entry_price = None
                days_held = 0

        elif not in_trade:
            best_ticker = None
            most_negative_z = -1.5  # threshold

            for asset in prices:
                z = float(z_score[asset].iloc[i]) if pd.notna(z_score[asset].iloc[i]) else 0
                price = float(pm[asset].iloc[i])
                ma = float(ma20[asset].iloc[i]) if pd.notna(ma20[asset].iloc[i]) else price

                # Oversold (z < -1.5) but trend intact (above 20d MA)
                if z < most_negative_z and price > ma:
                    most_negative_z = z
                    best_ticker = asset

            if best_ticker:
                price = float(pm[best_ticker].iloc[i])
                result = portfolio.buy(best_ticker, dollars=portfolio.cash * 0.85, date=date_str)
                if result:
                    in_trade = True
                    trade_ticker = best_ticker
                    entry_price = price
                    days_held = 0

    if in_trade:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(trade_ticker, all_shares=True, date=last_date)
