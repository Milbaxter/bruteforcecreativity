"""
Commodity-Equity Spread: Trade the divergence between commodity prices and
equity markets. When commodities (GLD+USO average) are rising faster than
SPY, rotate into commodity ETFs. When equities are winning, ride QQQ.

This captures the commodity supercycle vs tech rally tug-of-war.
"""

import pandas as pd

STRATEGY = {
    "name": "Commodity-Equity Spread",
    "hypothesis": "When the commodity basket outperforms equities over 7 days, commodity momentum persists. When equities lead, tech momentum persists. The spread signals regime.",
    "universe": ["GLD", "USO", "QQQ", "SPY"],
    "entry": "Buy GLD when commodity basket 7-day return > SPY; buy QQQ otherwise",
    "exit": "Rotate every 3 trading days",
    "position_size": "90% of cash",
    "eccentricity": "Commodity vs equity relative value as a timing signal. Simple but effective in capturing macro regime shifts that take weeks to play out.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    gld = data_fetcher.get_prices("GLD", start=start_date, end=end_date)
    uso = data_fetcher.get_prices("USO", start=start_date, end=end_date)
    qqq = data_fetcher.get_prices("QQQ", start=start_date, end=end_date)
    spy = data_fetcher.get_prices("SPY", start=start_date, end=end_date)

    for name, df in [("gld", gld), ("uso", uso), ("qqq", qqq), ("spy", spy)]:
        if isinstance(df.columns, pd.MultiIndex):
            if name == "gld":
                gld.columns = gld.columns.get_level_values(0)
            elif name == "uso":
                uso.columns = uso.columns.get_level_values(0)
            elif name == "qqq":
                qqq.columns = qqq.columns.get_level_values(0)
            else:
                spy.columns = spy.columns.get_level_values(0)

    gld_close = gld["Close"]
    uso_close = uso["Close"]
    qqq_close = qqq["Close"]
    spy_close = spy["Close"]

    common = sorted(
        set(gld_close.index) & set(uso_close.index) &
        set(qqq_close.index) & set(spy_close.index)
    )
    if len(common) < 12:
        return

    current_holding = None
    hold_counter = 0

    for i in range(7, len(common)):
        day = common[i]
        day_str = day.strftime("%Y-%m-%d") if hasattr(day, "strftime") else str(day)[:10]

        if current_holding:
            hold_counter += 1

        if hold_counter >= 3 or current_holding is None:
            lookback = common[i - 7]

            # Commodity basket return (avg of GLD and USO)
            gld_ret = (float(gld_close.loc[day]) - float(gld_close.loc[lookback])) / float(gld_close.loc[lookback])
            uso_ret = (float(uso_close.loc[day]) - float(uso_close.loc[lookback])) / float(uso_close.loc[lookback])
            commodity_ret = (gld_ret + uso_ret) / 2

            # Equity return
            spy_ret = (float(spy_close.loc[day]) - float(spy_close.loc[lookback])) / float(spy_close.loc[lookback])

            # Pick regime
            if commodity_ret > spy_ret:
                target = "GLD"  # Commodity regime — ride gold (more liquid than USO)
            else:
                target = "QQQ"  # Equity regime — ride tech

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
