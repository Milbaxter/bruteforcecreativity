"""
VIX Contrarian Fast — contrarian VIX allocation with enforced fast rotation.

Thesis: Same as Contrarian VIX Alloc (which had 54% return, 1.55 Sharpe but failed
on 16.5-day avg hold). Fix: force rotation every 5 days AND use tighter thresholds:
- VIX > 20: Buy QQQ (contrarian — fear creates opportunity, not just above 22)
- VIX < 16: Buy SLV (equities calm, find alternative alpha in silver)
- VIX 16-20: Buy XLF (moderate, banks benefit from stable rates)

The tighter thresholds (20 instead of 22 for fear entry) and forced 5-day rotation
should reduce average holding period while maintaining the alpha.

No 2-day confirmation — act immediately to reduce lag and holding time.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "VIX Contrarian Fast",
    "hypothesis": "Contrarian VIX: QQQ on fear (>20), SLV on calm (<16), XLF moderate. Forced 5-day rotation max.",
    "universe": ["QQQ", "SLV", "XLF", "SPY"],
    "entry": "QQQ when VIX > 20, SLV when VIX < 16, XLF when 16-20. Rotate every 3 days, max 5-day hold.",
    "exit": "Rotate every 3 days or max 5-day hold",
    "position_size": "90% of capital",
    "eccentricity": "Contrarian VIX with fast forced rotation. Buy equities when scared, commodities when calm. Opposite of conventional wisdom.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    vix = data_fetcher.get_vix(start=start_date, end=end_date)
    prices = {}
    for a in ["QQQ", "SLV", "XLF"]:
        df = data_fetcher.get_prices(a, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            prices[a] = s

    if len(prices) < 3 or vix.empty:
        return

    vix.index = pd.to_datetime(vix.index)
    common = None
    for s in prices.values():
        common = s.index if common is None else common.intersection(s.index)
    common = common.intersection(vix.index)
    if common is None or len(common) < 10:
        return
    common = common.sort_values()

    vix_c = vix.loc[common]

    current_holding = None
    rotation_day = 0
    hold_days = 0

    for i in range(0, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        v = float(vix_c.iloc[i])
        rotation_day += 1
        if current_holding:
            hold_days += 1

        # Force rotation check every 3 days or at max 5-day hold
        if rotation_day < 3 and hold_days < 5 and current_holding is not None:
            continue

        # Determine target
        if v > 20:
            target = "QQQ"
        elif v < 16:
            target = "SLV"
        else:
            target = "XLF"

        if target != current_holding or hold_days >= 5:
            if current_holding:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
            portfolio.buy(target, dollars=portfolio.cash * 0.9, date=date_str)
            current_holding = target
            rotation_day = 0
            hold_days = 0

    if current_holding:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(current_holding, all_shares=True, date=last_date)
