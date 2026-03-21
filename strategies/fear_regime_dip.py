"""
Fear Regime Dip Buyer — crypto fear/greed selects the asset, pullback timing selects entry.

Thesis: Two independent alpha sources combined:
1. REGIME SELECTION: Crypto fear/greed determines which asset to focus on
   - Fear (< 30): focus on QQQ (contrarian — fear creates equity opportunity)
   - Moderate (30-60): focus on XLF (banks in stable conditions)
   - Greed (> 60): focus on SLV (diversify away from overextended risk assets)

2. ENTRY TIMING: Within the selected asset, only buy when there's a 2%+ pullback
   from the 10-day high (pullback in uptrend for better entry)

The regime selection is macro (what to buy), the pullback is micro (when to buy).
Neither signal alone is sufficient — together they filter for high-quality setups.

Hold 5 days after entry. -2% stop loss.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Fear Regime Dip Buyer",
    "hypothesis": "Crypto fear selects the asset (QQQ on fear, SLV on greed, XLF moderate). Pullback timing selects the entry. Two independent alpha sources.",
    "universe": ["QQQ", "SLV", "XLF", "SPY"],
    "entry": "When selected asset pulls back 2%+ from 10d high AND price > 20d MA. Fear selects which asset.",
    "exit": "Sell after 5 days or +3%/-2% stop",
    "position_size": "85% of capital per trade",
    "eccentricity": "Regime signal (crypto fear) for asset SELECTION + pullback for entry TIMING. Two independent alpha sources layered together.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    crypto_fg = data_fetcher.get_crypto_fear_greed(days=400)

    prices = {}
    for a in ["QQQ", "SLV", "XLF"]:
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
    if common is None or len(common) < 25:
        return
    common = common.sort_values()

    fg_aligned = crypto_fg.reindex(common, method="ffill")

    pm = pd.DataFrame({a: prices[a].loc[common] for a in prices})
    high_10d = pm.rolling(10).max()
    pullback = (pm - high_10d) / high_10d
    ma_20d = pm.rolling(20).mean()

    in_trade = False
    trade_ticker = None
    entry_price = None
    days_held = 0

    for i in range(25, len(common)):
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
            fg = float(fg_aligned.iloc[i]) if pd.notna(fg_aligned.iloc[i]) else 50

            # Select asset based on fear/greed
            if fg < 30:
                target_asset = "QQQ"
            elif fg > 60:
                target_asset = "SLV"
            else:
                target_asset = "XLF"

            # Check pullback + trend for the selected asset
            price = float(pm[target_asset].iloc[i])
            pb = float(pullback[target_asset].iloc[i]) if pd.notna(pullback[target_asset].iloc[i]) else 0
            ma = float(ma_20d[target_asset].iloc[i]) if pd.notna(ma_20d[target_asset].iloc[i]) else price

            if pb < -0.02 and price > ma:
                result = portfolio.buy(target_asset, dollars=portfolio.cash * 0.85, date=date_str)
                if result:
                    in_trade = True
                    trade_ticker = target_asset
                    entry_price = price
                    days_held = 0

    if in_trade:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(trade_ticker, all_shares=True, date=last_date)
