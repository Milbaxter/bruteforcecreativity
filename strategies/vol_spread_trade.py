"""
Vol Spread Trade — exploit the gap between implied (VIX) and realized volatility.

Thesis: VIX measures EXPECTED 30-day volatility; realized volatility is the ACTUAL
historical standard deviation of SPY returns. When VIX >> realized vol (spread > 5 points),
the market is overpricing fear. This gap typically closes by VIX falling (not realized
vol rising), which is bullish for equities.

Conversely, when realized vol approaches or exceeds VIX (spread < 2), the market is
complacent and not pricing in enough risk — time to be defensive.

Rotation every 3 days:
- Vol spread > 5 (VIX overpricing fear): Buy QQQ (fear normalization trade)
- Vol spread 2-5 (normal): Buy based on 5-day momentum leader (QQQ or TLT)
- Vol spread < 2 (complacency): Buy TLT (defensive)

Combined with a minimum VIX level filter (VIX > 14) to avoid acting in dead-calm markets
where the spread is meaningless.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Vol Spread Trade",
    "hypothesis": "When VIX far exceeds realized vol (spread > 5), fear is overpriced and will normalize down → buy QQQ. When spread < 2, complacency → buy TLT. 3-day rotation.",
    "universe": ["QQQ", "TLT", "SPY"],
    "entry": "Buy QQQ when VIX - realized vol > 5 and VIX > 14; buy TLT when spread < 2; momentum leader in between",
    "exit": "Rotate every 3 days",
    "position_size": "90% of capital",
    "eccentricity": "Implied vs realized vol spread is an institutional options signal applied to equity allocation. Retail doesn't compute realized vol; institutions express this through options, not equity positions.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    spy = data_fetcher.get_prices("SPY", start=start_date, end=end_date)
    vix = data_fetcher.get_vix(start=start_date, end=end_date)
    qqq = data_fetcher.get_prices("QQQ", start=start_date, end=end_date)
    tlt = data_fetcher.get_prices("TLT", start=start_date, end=end_date)

    if spy.empty or vix.empty or qqq.empty or tlt.empty:
        return

    spy_close = spy["Close"].dropna()
    qqq_close = qqq["Close"].dropna()
    tlt_close = tlt["Close"].dropna()

    spy_close.index = pd.to_datetime(spy_close.index)
    vix.index = pd.to_datetime(vix.index)
    qqq_close.index = pd.to_datetime(qqq_close.index)
    tlt_close.index = pd.to_datetime(tlt_close.index)

    common = spy_close.index.intersection(vix.index).intersection(qqq_close.index).intersection(tlt_close.index)
    if len(common) < 30:
        return
    common = common.sort_values()

    spy_c = spy_close.loc[common]
    vix_c = vix.loc[common]
    qqq_c = qqq_close.loc[common]
    tlt_c = tlt_close.loc[common]

    # Compute 20-day realized volatility (annualized, in VIX-comparable units)
    spy_returns = spy_c.pct_change()
    realized_vol = spy_returns.rolling(20).std() * np.sqrt(252) * 100  # annualized, in % points

    # Vol spread: VIX - realized vol
    vol_spread = vix_c - realized_vol

    # Momentum for tie-breaker
    qqq_ret5 = qqq_c.pct_change(5)
    tlt_ret5 = tlt_c.pct_change(5)

    current_holding = None
    rotation_day = 0

    for i in range(25, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        rotation_day += 1

        if rotation_day < 3 and current_holding is not None:
            continue

        vs = float(vol_spread.iloc[i]) if pd.notna(vol_spread.iloc[i]) else 3
        vix_level = float(vix_c.iloc[i])

        if vix_level < 14:
            # Dead calm — use momentum
            qr = float(qqq_ret5.iloc[i]) if pd.notna(qqq_ret5.iloc[i]) else 0
            tr = float(tlt_ret5.iloc[i]) if pd.notna(tlt_ret5.iloc[i]) else 0
            target = "QQQ" if qr > tr else "TLT"
        elif vs > 5:
            target = "QQQ"   # Fear overpriced
        elif vs < 2:
            target = "TLT"   # Complacency
        else:
            # Normal — momentum leader
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
