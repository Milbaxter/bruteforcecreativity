"""
Simple VIX Switch — QQQ below VIX 22, TLT above VIX 22.

Thesis: VIX ~20 is the dividing line between "calm" and "stressed" markets. This has
been a remarkably stable threshold for decades. Below 20-22: equities grind higher.
Above 22: risk of further selloff or at minimum, choppy markets where bonds outperform.

The strategy is intentionally dead simple:
- VIX closes below 20 for 2 consecutive days: switch to QQQ
- VIX closes above 22 for 2 consecutive days: switch to TLT
- Between 20-22: hold current position (hysteresis zone prevents whipsaw)

The 2-day confirmation filter avoids reacting to one-day VIX spikes that immediately
reverse. The hysteresis band (20 to enter QQQ, 22 to exit) prevents constant switching.

Simple approaches often survive walk-forward because they capture genuine persistent
patterns rather than overfitting to recent data.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Simple VIX Switch",
    "hypothesis": "VIX 20-22 is the dividing line between calm (QQQ) and stressed (TLT) markets. 2-day confirmation + hysteresis band prevents whipsaw.",
    "universe": ["QQQ", "TLT", "SPY"],
    "entry": "QQQ when VIX < 20 for 2 days. TLT when VIX > 22 for 2 days. Hold in between.",
    "exit": "Switch on VIX threshold crossings with 2-day confirmation",
    "position_size": "90% of capital",
    "eccentricity": "Deliberately simple — one signal, one threshold, two assets. VIX mean-reversion is the most persistent pattern in finance.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    qqq = data_fetcher.get_prices("QQQ", start=start_date, end=end_date)
    tlt = data_fetcher.get_prices("TLT", start=start_date, end=end_date)
    vix = data_fetcher.get_vix(start=start_date, end=end_date)

    if qqq.empty or tlt.empty or vix.empty:
        return

    qqq_close = qqq["Close"].dropna()
    tlt_close = tlt["Close"].dropna()
    qqq_close.index = pd.to_datetime(qqq_close.index)
    tlt_close.index = pd.to_datetime(tlt_close.index)
    vix.index = pd.to_datetime(vix.index)

    common = qqq_close.index.intersection(tlt_close.index).intersection(vix.index)
    if len(common) < 5:
        return
    common = common.sort_values()

    vix_c = vix.loc[common]

    current_holding = None
    consecutive_low = 0   # days VIX < 20
    consecutive_high = 0  # days VIX > 22

    for i in range(0, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        v = float(vix_c.iloc[i])

        # Track consecutive days
        if v < 20:
            consecutive_low += 1
            consecutive_high = 0
        elif v > 22:
            consecutive_high += 1
            consecutive_low = 0
        else:
            # In hysteresis zone — reset counters but keep position
            consecutive_low = 0
            consecutive_high = 0

        # Determine target
        target = current_holding
        if consecutive_low >= 2 and current_holding != "QQQ":
            target = "QQQ"
        elif consecutive_high >= 2 and current_holding != "TLT":
            target = "TLT"

        # Initial entry (start in QQQ if VIX is low, TLT otherwise)
        if current_holding is None:
            target = "QQQ" if v < 22 else "TLT"

        if target != current_holding:
            if current_holding:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
            portfolio.buy(target, dollars=portfolio.cash * 0.9, date=date_str)
            current_holding = target

    if current_holding:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(current_holding, all_shares=True, date=last_date)
