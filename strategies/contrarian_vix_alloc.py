"""
Contrarian VIX Allocation — invert the typical VIX playbook.

Thesis: The typical advice is "buy safety when VIX is high." But the CONTRARIAN approach
works better because VIX spikes are temporary (mean-reverting). When VIX > 20, fear
creates buying opportunity in QQQ. When VIX < 15, complacency means equities are maxed
out — look for alpha in alternatives (SLV, which has its own drivers).

Three levels:
- VIX > 22: Buy QQQ (contrarian — fear is temporary, buy the dip)
- VIX < 16: Buy SLV (equities fully valued, commodities offer alternative alpha)
- VIX 16-22: Buy XLF (moderate positioning in rate-sensitive financials)

The contrarian VIX approach works because:
1. VIX > 22 events resolve within days (VIX mean-reverts)
2. When VIX is low, equities have less upside but commodities move on their own drivers
3. XLF benefits from moderate volatility environments (loan demand, capital markets)

3-day rotation with 2-day confirmation to avoid whipsaw.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Contrarian VIX Alloc",
    "hypothesis": "Invert VIX playbook: high VIX = buy QQQ (fear is opportunity), low VIX = buy SLV (equities maxed, commodity alpha), medium = XLF.",
    "universe": ["QQQ", "SLV", "XLF", "SPY"],
    "entry": "QQQ when VIX > 22 for 2+ days, SLV when VIX < 16 for 2+ days, XLF when 16-22",
    "exit": "Rotate every 3 days based on VIX regime",
    "position_size": "90% of capital",
    "eccentricity": "Contrarian VIX interpretation — opposite of conventional wisdom. Fear = buy equities (mean reversion), calm = buy commodities (alternative alpha).",
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
    consecutive_high = 0
    consecutive_low = 0

    for i in range(0, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        v = float(vix_c.iloc[i])
        rotation_day += 1

        # Track consecutive days in zones
        if v > 22:
            consecutive_high += 1
            consecutive_low = 0
        elif v < 16:
            consecutive_low += 1
            consecutive_high = 0
        else:
            consecutive_high = 0
            consecutive_low = 0

        if rotation_day < 3 and current_holding is not None:
            continue

        # Determine target with 2-day confirmation
        if consecutive_high >= 2:
            target = "QQQ"   # Contrarian — fear is opportunity
        elif consecutive_low >= 2:
            target = "SLV"   # Low VIX — alternative alpha
        elif v >= 16 and v <= 22:
            target = "XLF"   # Moderate — banks
        else:
            target = current_holding or "XLF"  # Default moderate

        if target != current_holding:
            if current_holding:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
            portfolio.buy(target, dollars=portfolio.cash * 0.9, date=date_str)
            current_holding = target
            rotation_day = 0

    if current_holding:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(current_holding, all_shares=True, date=last_date)
