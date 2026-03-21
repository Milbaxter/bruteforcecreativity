"""
QQQ Risk Shield — stay in QQQ by default, exit only on extreme danger signals.

Thesis: The biggest drag on active strategies vs buy-and-hold is TIME OUT OF MARKET.
Markets go up ~70% of the time. Instead of trying to pick entries, stay invested in
QQQ (highest-returning major ETF) and only exit when clear danger signals fire.

The shield only triggers on extreme conditions:
1. VIX spikes > 28 (extreme fear territory)
2. QQQ drops > 2.5% in 2 days (rapid selloff in progress)
3. Both conditions must be true simultaneously (avoids false signals)

When shield triggers: sell QQQ, go to cash.
Re-enter: when VIX drops back below 22 AND QQQ has a positive 3-day return.

This means we stay invested ~90% of the time but dodge the 2-3 worst drawdowns.
When in cash, check daily for re-entry.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "QQQ Risk Shield",
    "hypothesis": "Stay invested in QQQ by default. Only exit on extreme danger (VIX > 28 + QQQ 2-day drop > 2.5%). Minimize time out of market while dodging worst drawdowns.",
    "universe": ["QQQ", "SPY"],
    "entry": "Buy QQQ on day 1. Re-enter when VIX < 22 AND QQQ 3-day return > 0 after a shield trigger.",
    "exit": "Only exit when VIX > 28 AND QQQ 2-day drop > 2.5%",
    "position_size": "95% of capital",
    "eccentricity": "Inverted approach — instead of finding entries, stay invested and only find exits. Minimizes opportunity cost which is the #1 alpha killer.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    qqq = data_fetcher.get_prices("QQQ", start=start_date, end=end_date)
    vix = data_fetcher.get_vix(start=start_date, end=end_date)

    if qqq.empty or vix.empty:
        return

    qqq_close = qqq["Close"].dropna()
    qqq_close.index = pd.to_datetime(qqq_close.index)
    vix.index = pd.to_datetime(vix.index)

    common = qqq_close.index.intersection(vix.index)
    if len(common) < 10:
        return
    common = common.sort_values()

    qqq_c = qqq_close.loc[common]
    vix_c = vix.loc[common]

    # Start invested immediately
    invested = False
    shield_active = False

    for i in range(3, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        vix_level = float(vix_c.iloc[i])

        if not invested and not shield_active:
            # First entry — buy QQQ
            portfolio.buy("QQQ", dollars=portfolio.cash * 0.95, date=date_str)
            invested = True
            continue

        if invested:
            # Check danger signals
            qqq_ret2 = (float(qqq_c.iloc[i]) - float(qqq_c.iloc[i-2])) / float(qqq_c.iloc[i-2])

            if vix_level > 28 and qqq_ret2 < -0.025:
                # DANGER — activate shield
                portfolio.sell("QQQ", all_shares=True, date=date_str)
                invested = False
                shield_active = True

        elif shield_active:
            # In cash — check re-entry
            qqq_ret3 = (float(qqq_c.iloc[i]) - float(qqq_c.iloc[i-3])) / float(qqq_c.iloc[i-3])

            if vix_level < 22 and qqq_ret3 > 0:
                portfolio.buy("QQQ", dollars=portfolio.cash * 0.95, date=date_str)
                invested = True
                shield_active = False

    # Close position at end
    if invested:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell("QQQ", all_shares=True, date=last_date)
