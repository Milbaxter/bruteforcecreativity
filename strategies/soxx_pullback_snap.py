"""
SOXX Pullback Snap — buy semiconductors on sharp pullbacks with volume confirmation.

Thesis: Semiconductors (SOXX) are the highest-beta major sector ETF. When SOXX pulls
back >3% from its 10-day high, the selloff is almost always an overreaction because:
(1) semis have strong secular demand trends (AI, data centers, automotive),
(2) institutional rebalancing creates mechanical buying pressure after sharp drops,
(3) semi stocks have high short interest creating squeeze potential on bounces.

Three signals:
1. SOXX pullback > 3% from 10-day high (sharp selloff)
2. Volume > 1.3x 20-day average (real selling, not thin-market drift)
3. VIX < 30 (not a systemic crisis where everything stays down)

Buy SOXX, hold 5 days or until recovery to within 1% of 10d high.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "SOXX Pullback Snap",
    "hypothesis": "SOXX pullback > 3% from 10d high + elevated volume + non-crisis VIX = overreaction that snaps back within 5 days.",
    "universe": ["SOXX", "SPY"],
    "entry": "Buy SOXX when price > 3% below 10d high AND volume > 1.3x 20d avg AND VIX < 30",
    "exit": "Sell after 5 days or when within 1% of 10d high or -3% stop loss",
    "position_size": "85% of capital per trade",
    "eccentricity": "Semiconductor-specific pullback pattern with volume confirmation. SOXX has higher beta than QQQ so pullbacks are sharper and bounces are bigger.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    soxx = data_fetcher.get_prices("SOXX", start=start_date, end=end_date)
    vix = data_fetcher.get_vix(start=start_date, end=end_date)

    if soxx.empty or vix.empty:
        return

    soxx.index = pd.to_datetime(soxx.index)
    vix.index = pd.to_datetime(vix.index)

    if not all(c in soxx.columns for c in ["Close", "Volume"]):
        return

    soxx_close = soxx["Close"]
    soxx_vol = soxx["Volume"]

    common = soxx_close.dropna().index.intersection(vix.index)
    if len(common) < 25:
        return
    common = common.sort_values()

    soxx_c = soxx_close.loc[common]
    soxx_v = soxx_vol.loc[common]
    vix_c = vix.loc[common]

    # Rolling 10-day high
    high_10d = soxx_c.rolling(10).max()
    # Pullback from high
    pullback_pct = (soxx_c - high_10d) / high_10d
    # Volume ratio
    vol_avg20 = soxx_v.rolling(20).mean()
    vol_ratio = soxx_v / vol_avg20

    in_trade = False
    entry_price = None
    days_held = 0

    for i in range(25, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        price = float(soxx_c.iloc[i])

        if in_trade:
            days_held += 1
            pnl_pct = (price - entry_price) / entry_price
            # Check if recovered to within 1% of 10d high
            h10 = float(high_10d.iloc[i]) if pd.notna(high_10d.iloc[i]) else price * 1.1
            recovery = (price - h10) / h10

            if days_held >= 5 or recovery > -0.01 or pnl_pct <= -0.03:
                portfolio.sell("SOXX", all_shares=True, date=date_str)
                in_trade = False
                entry_price = None
                days_held = 0

        elif not in_trade:
            pb = float(pullback_pct.iloc[i]) if pd.notna(pullback_pct.iloc[i]) else 0
            vr = float(vol_ratio.iloc[i]) if pd.notna(vol_ratio.iloc[i]) else 1
            vix_level = float(vix_c.iloc[i])

            if pb < -0.03 and vr > 1.3 and vix_level < 30:
                result = portfolio.buy("SOXX", dollars=portfolio.cash * 0.85, date=date_str)
                if result:
                    in_trade = True
                    entry_price = price
                    days_held = 0

    if in_trade:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell("SOXX", all_shares=True, date=last_date)
