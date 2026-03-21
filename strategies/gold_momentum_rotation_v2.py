"""
Gold Momentum Rotation v2: Faster version with 3-day rotation and 7-day lookback.

The original Gold Momentum Rotation returned 45% but avg hold was 15.9 days
(just over the 15-day limit). This version rotates every 3 trading days and
uses a 7-day lookback to keep hold periods shorter while maintaining the
gold-vs-equity regime signal.
"""

import pandas as pd

STRATEGY = {
    "name": "Gold Momentum Rotation v2",
    "hypothesis": "Gold vs SPY relative performance over 7 days signals risk regime. Faster 3-day rotation captures regime shifts more quickly while keeping holds short.",
    "universe": ["GLD", "QQQ", "SPY"],
    "entry": "Buy GLD when it outperforms SPY over 7 days; buy QQQ when SPY outperforms GLD",
    "exit": "Rotate every 3 trading days",
    "position_size": "90% of cash",
    "eccentricity": "Cross-asset regime detection with rapid rotation. Binary gold/tech switching that no fund would attempt at this frequency.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    gld = data_fetcher.get_prices("GLD", start=start_date, end=end_date)
    qqq = data_fetcher.get_prices("QQQ", start=start_date, end=end_date)
    spy = data_fetcher.get_prices("SPY", start=start_date, end=end_date)

    for name, df in [("gld", gld), ("qqq", qqq), ("spy", spy)]:
        if isinstance(df.columns, pd.MultiIndex):
            if name == "gld":
                gld.columns = gld.columns.get_level_values(0)
            elif name == "qqq":
                qqq.columns = qqq.columns.get_level_values(0)
            else:
                spy.columns = spy.columns.get_level_values(0)

    gld_close = gld["Close"]
    qqq_close = qqq["Close"]
    spy_close = spy["Close"]

    common = sorted(set(gld_close.index) & set(qqq_close.index) & set(spy_close.index))
    if len(common) < 10:
        return

    current_holding = None
    hold_counter = 0
    rotation_period = 3
    lookback_days = 7

    for i in range(lookback_days, len(common)):
        day = common[i]
        day_str = day.strftime("%Y-%m-%d") if hasattr(day, "strftime") else str(day)[:10]

        if current_holding:
            hold_counter += 1

        # Time to rotate?
        if hold_counter >= rotation_period or current_holding is None:
            lookback = common[i - lookback_days]

            gld_ret = (float(gld_close.loc[day]) - float(gld_close.loc[lookback])) / float(gld_close.loc[lookback])
            spy_ret = (float(spy_close.loc[day]) - float(spy_close.loc[lookback])) / float(spy_close.loc[lookback])

            if gld_ret > spy_ret:
                target = "GLD"
            else:
                target = "QQQ"

            if current_holding and current_holding != target:
                portfolio.sell(current_holding, all_shares=True, date=day_str)
                current_holding = None

            if current_holding is None:
                result = portfolio.buy(target, dollars=portfolio.cash * 0.90, date=day_str)
                if result:
                    current_holding = target
                    hold_counter = 0

    if current_holding and common:
        last = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(current_holding, all_shares=True, date=last)
