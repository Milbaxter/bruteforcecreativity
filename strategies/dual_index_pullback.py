"""
Dual Index Pullback: Buy both QQQ and SPY when either pulls back 1.5%+ from
its 5-day high. Faster parameters than Pullback Sniper to generate more trades.

Variation on the winning Pullback Sniper theme:
- Tighter entry: 1.5% pullback instead of 2% (more trades)
- Shorter lookback: 5-day high instead of 10-day
- Faster exit: 5 days max instead of 7
- Dual index: split between QQQ and SPY for diversification
"""

import pandas as pd

STRATEGY = {
    "name": "Dual Index Pullback",
    "hypothesis": "Pullbacks of 1.5%+ from 5-day highs in major indices get bought within 3-5 days. Splitting between QQQ and SPY provides diversification while maintaining the dip-buying edge.",
    "universe": ["SPY", "QQQ"],
    "entry": "Buy QQQ + SPY when either pulls back 1.5%+ from 5-day high",
    "exit": "Sell when price recovers to within 0.3% of 5-day high, or 5 days, or -3% stop",
    "position_size": "45% QQQ, 45% SPY per trade",
    "eccentricity": "Faster rotation version of index dip buying. The short lookback and tight entry make this too noisy for institutional systematic strategies.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    spy = data_fetcher.get_prices("SPY", start=start_date, end=end_date)
    qqq = data_fetcher.get_prices("QQQ", start=start_date, end=end_date)

    if isinstance(spy.columns, pd.MultiIndex):
        spy.columns = spy.columns.get_level_values(0)
    if isinstance(qqq.columns, pd.MultiIndex):
        qqq.columns = qqq.columns.get_level_values(0)

    spy_close = spy["Close"]
    qqq_close = qqq["Close"]

    common = sorted(set(spy_close.index) & set(qqq_close.index))
    if len(common) < 10:
        return

    in_position = False
    days_held = 0
    entry_spy_price = None
    entry_qqq_price = None

    for i in range(5, len(common)):
        day = common[i]
        day_str = day.strftime("%Y-%m-%d") if hasattr(day, "strftime") else str(day)[:10]

        spy_price = float(spy_close.loc[day])
        qqq_price = float(qqq_close.loc[day])

        # 5-day rolling high
        spy_highs = [float(spy_close.loc[common[j]]) for j in range(i - 5, i + 1)]
        qqq_highs = [float(qqq_close.loc[common[j]]) for j in range(i - 5, i + 1)]
        spy_high = max(spy_highs)
        qqq_high = max(qqq_highs)

        spy_dd = (spy_price - spy_high) / spy_high
        qqq_dd = (qqq_price - qqq_high) / qqq_high

        if in_position:
            days_held += 1

            spy_pct = (spy_price - entry_spy_price) / entry_spy_price if entry_spy_price else 0
            qqq_pct = (qqq_price - entry_qqq_price) / entry_qqq_price if entry_qqq_price else 0
            avg_pct = (spy_pct + qqq_pct) / 2

            # Exit: both recovered, or 5 days, or -3% average stop
            both_recovered = spy_dd > -0.003 and qqq_dd > -0.003
            if both_recovered or days_held >= 5 or avg_pct <= -0.03:
                portfolio.sell("SPY", all_shares=True, date=day_str)
                portfolio.sell("QQQ", all_shares=True, date=day_str)
                in_position = False
                days_held = 0
                entry_spy_price = None
                entry_qqq_price = None
        else:
            # Entry: either index pulling back 1.5%+
            if spy_dd <= -0.015 or qqq_dd <= -0.015:
                cash = portfolio.cash
                if cash < 200:
                    continue

                r1 = portfolio.buy("SPY", dollars=cash * 0.45, date=day_str)
                r2 = portfolio.buy("QQQ", dollars=portfolio.cash * 0.80, date=day_str)

                if r1 or r2:
                    in_position = True
                    days_held = 0
                    entry_spy_price = spy_price
                    entry_qqq_price = qqq_price

    # Close remaining
    if in_position and common:
        last = common[-1].strftime("%Y-%m-%d")
        portfolio.sell("SPY", all_shares=True, date=last)
        portfolio.sell("QQQ", all_shares=True, date=last)
