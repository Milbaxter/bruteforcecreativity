"""
Global Risk Barometer — use BTC + China tech as dual risk signals for US tech allocation.

Thesis: Bitcoin and Chinese tech (KWEB) are two of the most risk-sensitive assets in
global markets but from completely different ecosystems (crypto vs EM equities). When
BOTH are showing positive momentum simultaneously, it's a strong global risk-on signal
that tends to benefit QQQ over the next 3-5 days. When both are negative, go to cash.
When they disagree, allocate to TLT (uncertainty favors bonds).

This is a continuous allocation strategy that rotates every 3 days between:
- QQQ (both BTC and KWEB 5-day momentum positive)
- TLT (signals disagree — one up, one down)
- Cash (both negative)

Three signals per rotation:
1. BTC 5-day momentum direction
2. KWEB 5-day momentum direction
3. Combined regime → allocation decision
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Global Risk Barometer",
    "hypothesis": "BTC + KWEB dual momentum as global risk-on/off barometer. Both up = QQQ, disagree = TLT, both down = cash. 3-day rotation.",
    "universe": ["QQQ", "TLT", "BTC-USD", "KWEB", "SPY"],
    "entry": "Buy QQQ when BTC and KWEB both have positive 5-day momentum; buy TLT when they disagree",
    "exit": "Rotate every 3 trading days based on updated signals",
    "position_size": "90% of capital",
    "eccentricity": "Crypto + Chinese tech as dual global risk barometer for US tech allocation. Nobody combines these two asset classes for rotation signals.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    btc = data_fetcher.get_prices("BTC-USD", start=start_date, end=end_date)
    kweb = data_fetcher.get_prices("KWEB", start=start_date, end=end_date)
    qqq = data_fetcher.get_prices("QQQ", start=start_date, end=end_date)
    tlt = data_fetcher.get_prices("TLT", start=start_date, end=end_date)

    if btc.empty or kweb.empty or qqq.empty or tlt.empty:
        return

    btc_close = btc["Close"].dropna()
    kweb_close = kweb["Close"].dropna()
    qqq_close = qqq["Close"].dropna()
    tlt_close = tlt["Close"].dropna()

    btc_close.index = pd.to_datetime(btc_close.index)
    kweb_close.index = pd.to_datetime(kweb_close.index)
    qqq_close.index = pd.to_datetime(qqq_close.index)
    tlt_close.index = pd.to_datetime(tlt_close.index)

    # Use QQQ trading days as base
    common = qqq_close.index.intersection(kweb_close.index).intersection(tlt_close.index)
    btc_aligned = btc_close.reindex(common, method="ffill")

    if len(common) < 15:
        return

    qqq_c = qqq_close.loc[common]
    kweb_c = kweb_close.loc[common]
    tlt_c = tlt_close.loc[common]
    btc_c = btc_aligned

    # 5-day returns
    btc_ret5 = btc_c.pct_change(5)
    kweb_ret5 = kweb_c.pct_change(5)

    current_holding = None  # "QQQ", "TLT", or None
    rotation_day = 0

    for i in range(7, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        rotation_day += 1

        if rotation_day < 3 and current_holding is not None:
            continue

        # Time to evaluate and possibly rotate
        br = float(btc_ret5.iloc[i]) if pd.notna(btc_ret5.iloc[i]) else 0
        kr = float(kweb_ret5.iloc[i]) if pd.notna(kweb_ret5.iloc[i]) else 0

        btc_positive = br > 0
        kweb_positive = kr > 0

        # Determine target allocation
        if btc_positive and kweb_positive:
            target = "QQQ"
        elif not btc_positive and not kweb_positive:
            target = None  # cash
        else:
            target = "TLT"  # disagreement

        # Rotate if needed
        if target != current_holding:
            # Sell current
            if current_holding:
                portfolio.sell(current_holding, all_shares=True, date=date_str)

            # Buy new target
            if target:
                portfolio.buy(target, dollars=portfolio.cash * 0.9, date=date_str)

            current_holding = target
            rotation_day = 0

    # Close remaining
    if current_holding:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(current_holding, all_shares=True, date=last_date)
