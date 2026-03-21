"""
BTC Volatility Regime — Bitcoin's realized volatility as a global risk barometer.

Thesis: Bitcoin trades 24/7 and reacts to global risk events faster than equities. Its
REALIZED VOLATILITY (not price direction) is a pure measure of global uncertainty. When
BTC vol is low, global markets are calm and growth-sensitive assets (SOXX) outperform.
When BTC vol is high, uncertainty is elevated and defensive assets (TLT) outperform.

This is different from using BTC PRICE as a signal (which just tracks risk-on/off).
BTC VOLATILITY captures UNCERTAINTY — even if BTC is going up, if it's doing so with
high volatility, the market is uncertain and that uncertainty bleeds into equities.

Rotation every 3 days:
- BTC 20d realized vol < 30th percentile (rolling 90d): Calm → SOXX (growth cyclical)
- BTC 20d realized vol between 30th-70th percentile: Moderate → XHB (rate-sensitive)
- BTC 20d realized vol > 70th percentile: Uncertain → TLT (safe haven)

Each asset responds to a different part of the risk spectrum.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "BTC Vol Regime",
    "hypothesis": "Bitcoin realized volatility (not price) measures global uncertainty. Low BTC vol = calm (buy SOXX). High BTC vol = uncertain (buy TLT). Medium = XHB. 3-day rotation.",
    "universe": ["SOXX", "XHB", "TLT", "BTC-USD", "SPY"],
    "entry": "SOXX when BTC vol < 30th pctile, XHB when 30th-70th, TLT when > 70th. Rotation every 3 days.",
    "exit": "Rotate every 3 days",
    "position_size": "90% of capital",
    "eccentricity": "BTC volatility (not price) as regime signal for non-crypto equity allocation. Nobody trades semiconductors based on Bitcoin's realized vol.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    btc = data_fetcher.get_prices("BTC-USD", start=start_date, end=end_date)
    soxx = data_fetcher.get_prices("SOXX", start=start_date, end=end_date)
    xhb = data_fetcher.get_prices("XHB", start=start_date, end=end_date)
    tlt = data_fetcher.get_prices("TLT", start=start_date, end=end_date)

    if btc.empty or soxx.empty or xhb.empty or tlt.empty:
        return

    btc_close = btc["Close"].dropna()
    btc_close.index = pd.to_datetime(btc_close.index)

    # Use equity trading days
    soxx_close = soxx["Close"].dropna()
    xhb_close = xhb["Close"].dropna()
    tlt_close = tlt["Close"].dropna()
    soxx_close.index = pd.to_datetime(soxx_close.index)
    xhb_close.index = pd.to_datetime(xhb_close.index)
    tlt_close.index = pd.to_datetime(tlt_close.index)

    common = soxx_close.index.intersection(xhb_close.index).intersection(tlt_close.index)
    btc_aligned = btc_close.reindex(common, method="ffill")

    if len(common) < 100:
        return

    # BTC daily returns and 20-day realized vol
    btc_ret = btc_aligned.pct_change()
    btc_vol_20d = btc_ret.rolling(20).std() * np.sqrt(365) * 100  # annualized %

    current_holding = None
    rotation_day = 0

    for i in range(95, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        rotation_day += 1

        if rotation_day < 3 and current_holding is not None:
            continue

        vol = float(btc_vol_20d.iloc[i]) if pd.notna(btc_vol_20d.iloc[i]) else 50

        # Rolling 90-day percentile of BTC vol
        vol_history = btc_vol_20d.iloc[max(0, i-90):i+1].dropna()
        if len(vol_history) < 20:
            continue

        percentile = float((vol_history < vol).sum() / len(vol_history) * 100)

        if percentile < 30:
            target = "SOXX"   # Low vol = calm = growth
        elif percentile > 70:
            target = "TLT"    # High vol = uncertain = defensive
        else:
            target = "XHB"    # Medium = moderate growth (rate-sensitive)

        if target != current_holding:
            if current_holding:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
            portfolio.buy(target, dollars=portfolio.cash * 0.9, date=date_str)
            current_holding = target
            rotation_day = 0

    if current_holding:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(current_holding, all_shares=True, date=last_date)
