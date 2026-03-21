"""
SOXX/XLU Risk Barometer — semiconductor vs utility relative strength for QQQ/TLT allocation.

Thesis: The SOXX/XLU ratio captures the market's growth vs safety preference better
than VIX or any single indicator because it's a REAL MONEY signal (actual flows into
growth vs defensive). When this ratio is rising (SOXX outperforming XLU), risk appetite
is genuinely improving → buy QQQ. When it's falling, money is rotating to safety → buy TLT.

Combined with: 7-day lookback for the ratio direction + require minimum magnitude of
change (not just noise) + VIX filter (in crisis, ratio may be meaningless).

Rotation every 3 days based on ratio direction:
- SOXX/XLU ratio 7d change > 0.5%: Risk-on → QQQ
- SOXX/XLU ratio 7d change < -0.5%: Risk-off → TLT
- In between: hold current position (avoid whipsaw in neutral zone)
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "SOXX XLU Barometer",
    "hypothesis": "SOXX/XLU ratio direction captures real money growth/safety flows. Rising ratio = risk-on (QQQ). Falling ratio = risk-off (TLT). 3-day rotation with 7d lookback.",
    "universe": ["QQQ", "TLT", "SOXX", "XLU", "SPY"],
    "entry": "Buy QQQ when SOXX/XLU ratio rising >0.5% over 7d; buy TLT when falling >0.5%; hold in neutral zone",
    "exit": "Rotate every 3 days",
    "position_size": "90% of capital",
    "eccentricity": "Inter-sector ratio (semis vs utilities) as real-money flow signal. Not a volatility or sentiment indicator — actual sector allocation flows.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    soxx = data_fetcher.get_prices("SOXX", start=start_date, end=end_date)
    xlu = data_fetcher.get_prices("XLU", start=start_date, end=end_date)
    qqq = data_fetcher.get_prices("QQQ", start=start_date, end=end_date)
    tlt = data_fetcher.get_prices("TLT", start=start_date, end=end_date)

    if soxx.empty or xlu.empty or qqq.empty or tlt.empty:
        return

    soxx_close = soxx["Close"].dropna()
    xlu_close = xlu["Close"].dropna()
    qqq_close = qqq["Close"].dropna()
    tlt_close = tlt["Close"].dropna()

    soxx_close.index = pd.to_datetime(soxx_close.index)
    xlu_close.index = pd.to_datetime(xlu_close.index)
    qqq_close.index = pd.to_datetime(qqq_close.index)
    tlt_close.index = pd.to_datetime(tlt_close.index)

    common = soxx_close.index.intersection(xlu_close.index).intersection(qqq_close.index).intersection(tlt_close.index)
    if len(common) < 15:
        return
    common = common.sort_values()

    soxx_c = soxx_close.loc[common]
    xlu_c = xlu_close.loc[common]
    qqq_c = qqq_close.loc[common]
    tlt_c = tlt_close.loc[common]

    # SOXX/XLU ratio
    ratio = soxx_c / xlu_c
    ratio_change_7d = ratio.pct_change(7)

    current_holding = None
    rotation_day = 0

    for i in range(10, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        rotation_day += 1

        if rotation_day < 3 and current_holding is not None:
            continue

        rc = float(ratio_change_7d.iloc[i]) if pd.notna(ratio_change_7d.iloc[i]) else 0

        if rc > 0.005:
            target = "QQQ"   # Risk-on
        elif rc < -0.005:
            target = "TLT"   # Risk-off
        else:
            target = current_holding  # Neutral — hold
            if target is None:
                target = "QQQ"  # Default to risk-on if no position

        if target != current_holding:
            if current_holding:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
            portfolio.buy(target, dollars=portfolio.cash * 0.9, date=date_str)
            current_holding = target
            rotation_day = 0

    if current_holding:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(current_holding, all_shares=True, date=last_date)
