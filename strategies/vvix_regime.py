"""
VVIX Regime — use volatility-of-volatility as a regime signal for QQQ/TLT allocation.

Thesis: VVIX (the VIX of the VIX) measures uncertainty about future volatility. When
VVIX is high but VIX is moderate, the options market is pricing in uncertainty about
direction — a vol spike is likely, so position defensively in TLT. When VVIX is low
and VIX is low, it's complacency — buy QQQ for continued calm/momentum. When both
are high, it's a crisis — stay in cash/TLT.

This is a 3-day rotation strategy:
- VVIX < 90 AND VIX < 20: Complacency → QQQ (ride momentum)
- VVIX > 110 AND VIX < 25: Uncertainty brewing → TLT (protect)
- VVIX > 110 AND VIX > 25: Crisis → TLT (safe haven)
- Otherwise: hold the 5-day momentum leader between QQQ and TLT

Eccentricity: Almost nobody watches VVIX. It's a second-derivative indicator that
options market makers use internally but retail investors completely ignore.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "VVIX Regime",
    "hypothesis": "VVIX level classifies market uncertainty regime. Low VVIX + low VIX = complacency (buy QQQ). High VVIX = uncertainty (buy TLT). 3-day rotation.",
    "universe": ["QQQ", "TLT", "SPY"],
    "entry": "Buy QQQ on complacency (VVIX < 90, VIX < 20), TLT on uncertainty (VVIX > 110), momentum leader otherwise",
    "exit": "Rotate every 3 trading days",
    "position_size": "90% of capital",
    "eccentricity": "VVIX (vol-of-vol) is a second-derivative indicator ignored by retail. Uses it as primary regime signal for asset allocation.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Fetch VVIX
    vvix_df = data_fetcher.get_prices("^VVIX", start=start_date, end=end_date)
    vix = data_fetcher.get_vix(start=start_date, end=end_date)
    qqq = data_fetcher.get_prices("QQQ", start=start_date, end=end_date)
    tlt = data_fetcher.get_prices("TLT", start=start_date, end=end_date)

    if vvix_df.empty or vix.empty or qqq.empty or tlt.empty:
        return

    vvix = vvix_df["Close"].dropna() if "Close" in vvix_df.columns else pd.Series(dtype=float)
    if vvix.empty:
        return

    qqq_close = qqq["Close"].dropna()
    tlt_close = tlt["Close"].dropna()

    vvix.index = pd.to_datetime(vvix.index)
    vix.index = pd.to_datetime(vix.index)
    qqq_close.index = pd.to_datetime(qqq_close.index)
    tlt_close.index = pd.to_datetime(tlt_close.index)

    common = vvix.index.intersection(vix.index).intersection(qqq_close.index).intersection(tlt_close.index)
    if len(common) < 15:
        return
    common = common.sort_values()

    vvix_c = vvix.loc[common]
    vix_c = vix.loc[common]
    qqq_c = qqq_close.loc[common]
    tlt_c = tlt_close.loc[common]

    # Momentum for tie-breaker
    qqq_ret5 = qqq_c.pct_change(5)
    tlt_ret5 = tlt_c.pct_change(5)

    current_holding = None
    rotation_day = 0

    for i in range(7, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        rotation_day += 1

        if rotation_day < 3 and current_holding is not None:
            continue

        vvix_level = float(vvix_c.iloc[i])
        vix_level = float(vix_c.iloc[i])

        # Determine regime
        if vvix_level < 90 and vix_level < 20:
            target = "QQQ"  # complacency
        elif vvix_level > 110 and vix_level > 25:
            target = "TLT"  # crisis
        elif vvix_level > 110:
            target = "TLT"  # uncertainty brewing
        else:
            # Mixed — go with momentum leader
            qr = float(qqq_ret5.iloc[i]) if pd.notna(qqq_ret5.iloc[i]) else 0
            tr = float(tlt_ret5.iloc[i]) if pd.notna(tlt_ret5.iloc[i]) else 0
            target = "QQQ" if qr > tr else "TLT"

        if target != current_holding:
            if current_holding:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
            portfolio.buy(target, dollars=portfolio.cash * 0.9, date=date_str)
            current_holding = target
            rotation_day = 0

    if current_holding:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(current_holding, all_shares=True, date=last_date)
