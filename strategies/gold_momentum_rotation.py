"""
Gold Momentum Rotation: When gold (GLD) is outperforming SPY over 10 days,
rotate into GLD. When SPY is outperforming, rotate into QQQ.

Thesis: Gold outperformance signals risk-off regime shifts (geopolitical risk,
inflation fears, rate uncertainty). During risk-off, gold momentum persists.
During risk-on (SPY outperforming), tech/growth (QQQ) is the best momentum play.

This is a simple regime-switching model that captures the dominant theme.
"""

import pandas as pd

STRATEGY = {
    "name": "Gold Momentum Rotation",
    "hypothesis": "Gold vs SPY relative performance signals risk regime. Gold outperforming = risk-off (ride gold). SPY outperforming = risk-on (ride QQQ for max momentum).",
    "universe": ["GLD", "QQQ", "SPY"],
    "entry": "Buy GLD when it outperforms SPY over 10 days; buy QQQ when SPY outperforms GLD",
    "exit": "Rotate every 5 trading days based on updated relative performance",
    "position_size": "90% of cash in the regime winner",
    "eccentricity": "Cross-asset regime detection using gold as the canary. Simple but effective — most funds can't rapidly switch between gold and tech. Too binary for institutional allocation models.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    gld = data_fetcher.get_prices("GLD", start=start_date, end=end_date)
    qqq = data_fetcher.get_prices("QQQ", start=start_date, end=end_date)
    spy = data_fetcher.get_prices("SPY", start=start_date, end=end_date)

    for df_name, df in [("gld", gld), ("qqq", qqq), ("spy", spy)]:
        if isinstance(df.columns, pd.MultiIndex):
            if df_name == "gld":
                gld.columns = gld.columns.get_level_values(0)
            elif df_name == "qqq":
                qqq.columns = qqq.columns.get_level_values(0)
            else:
                spy.columns = spy.columns.get_level_values(0)

    gld_close = gld["Close"]
    qqq_close = qqq["Close"]
    spy_close = spy["Close"]

    common = sorted(set(gld_close.index) & set(qqq_close.index) & set(spy_close.index))
    if len(common) < 15:
        return

    current_holding = None
    hold_counter = 0
    rotation_period = 5

    for i in range(10, len(common)):
        day = common[i]
        day_str = day.strftime("%Y-%m-%d") if hasattr(day, "strftime") else str(day)[:10]

        if current_holding:
            hold_counter += 1

        # Time to rotate?
        if hold_counter >= rotation_period or current_holding is None:
            lookback = common[i - 10]

            gld_ret = (float(gld_close.loc[day]) - float(gld_close.loc[lookback])) / float(gld_close.loc[lookback])
            spy_ret = (float(spy_close.loc[day]) - float(spy_close.loc[lookback])) / float(spy_close.loc[lookback])

            # Determine regime
            if gld_ret > spy_ret:
                target = "GLD"  # Risk-off: ride gold momentum
            else:
                target = "QQQ"  # Risk-on: ride tech momentum

            # Rotate if needed
            if current_holding and current_holding != target:
                portfolio.sell(current_holding, all_shares=True, date=day_str)
                current_holding = None

            if current_holding is None:
                result = portfolio.buy(target, dollars=portfolio.cash * 0.90, date=day_str)
                if result:
                    current_holding = target
                    hold_counter = 0

    # Close remaining
    if current_holding and common:
        last = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(current_holding, all_shares=True, date=last)
