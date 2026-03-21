"""
Bond-Equity Correlation Regime — use TLT/SPY rolling correlation as a regime signal.

Thesis: Normally, bonds and equities are negatively correlated (TLT goes up when SPY
goes down). When this relationship BREAKS (correlation turns positive), it's a major
regime signal:
- Both rising (positive corr, both up) = liquidity-driven rally → ride QQQ hard
- Both falling (positive corr, both down) = everything selling off → cash/defensive
- Normal negative correlation = standard regime → buy momentum leader

The correlation regime captures something VIX and other signals miss: the STRUCTURE
of cross-asset relationships, not just levels.

Rolling 20-day correlation with 5-day momentum to determine direction.
Rotation every 3 days.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Bond Equity Corr Regime",
    "hypothesis": "TLT/SPY rolling 20d correlation captures cross-asset regime shifts. Positive correlation + both up = liquidity rally (QQQ). Positive corr + both down = crisis (TLT). Normal negative corr = momentum leader.",
    "universe": ["QQQ", "TLT", "SPY"],
    "entry": "Regime-based: positive corr + both rising = QQQ, positive corr + both falling = TLT, negative corr = momentum leader",
    "exit": "Rotate every 3 days",
    "position_size": "90% of capital",
    "eccentricity": "Cross-asset correlation structure as regime signal. Not level-based — captures relationship regime shifts that VIX misses.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    spy = data_fetcher.get_prices("SPY", start=start_date, end=end_date)
    tlt = data_fetcher.get_prices("TLT", start=start_date, end=end_date)
    qqq = data_fetcher.get_prices("QQQ", start=start_date, end=end_date)

    if spy.empty or tlt.empty or qqq.empty:
        return

    spy_close = spy["Close"].dropna()
    tlt_close = tlt["Close"].dropna()
    qqq_close = qqq["Close"].dropna()

    spy_close.index = pd.to_datetime(spy_close.index)
    tlt_close.index = pd.to_datetime(tlt_close.index)
    qqq_close.index = pd.to_datetime(qqq_close.index)

    common = spy_close.index.intersection(tlt_close.index).intersection(qqq_close.index)
    if len(common) < 30:
        return
    common = common.sort_values()

    spy_c = spy_close.loc[common]
    tlt_c = tlt_close.loc[common]
    qqq_c = qqq_close.loc[common]

    # Daily returns
    spy_ret = spy_c.pct_change()
    tlt_ret = tlt_c.pct_change()

    # 20-day rolling correlation
    corr_20d = spy_ret.rolling(20).corr(tlt_ret)

    # 5-day returns for direction
    spy_ret5 = spy_c.pct_change(5)
    tlt_ret5 = tlt_c.pct_change(5)
    qqq_ret5 = qqq_c.pct_change(5)

    current_holding = None
    rotation_day = 0

    for i in range(25, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        rotation_day += 1

        if rotation_day < 3 and current_holding is not None:
            continue

        corr = float(corr_20d.iloc[i]) if pd.notna(corr_20d.iloc[i]) else -0.3
        sr5 = float(spy_ret5.iloc[i]) if pd.notna(spy_ret5.iloc[i]) else 0
        tr5 = float(tlt_ret5.iloc[i]) if pd.notna(tlt_ret5.iloc[i]) else 0
        qr5 = float(qqq_ret5.iloc[i]) if pd.notna(qqq_ret5.iloc[i]) else 0

        if corr > 0.2:
            # Unusual positive correlation
            if sr5 > 0 and tr5 > 0:
                target = "QQQ"  # Liquidity rally — ride it
            else:
                target = "TLT"  # Both falling or mixed — defensive
        else:
            # Normal negative correlation — go with momentum leader
            target = "QQQ" if qr5 > tr5 else "TLT"

        if target != current_holding:
            if current_holding:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
            portfolio.buy(target, dollars=portfolio.cash * 0.9, date=date_str)
            current_holding = target
            rotation_day = 0

    if current_holding:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(current_holding, all_shares=True, date=last_date)
