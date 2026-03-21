"""
Oil Gold Macro Switch v2: Refined version with 7-day ratio lookback and
tighter thresholds. The v1 had Sharpe exactly 1.0 — this aims to push
it higher by reducing whipsaws with a slightly longer lookback.
"""

import pandas as pd

STRATEGY = {
    "name": "Oil Gold Macro v2",
    "hypothesis": "7-day gold/oil ratio change with 1.5% threshold reduces whipsaws compared to v1's 5-day/2% setup, improving risk-adjusted returns.",
    "universe": ["GLD", "USO", "XLE", "QQQ"],
    "entry": "Buy GLD when 7-day gold/oil ratio rises >1.5%; XLE when falls >1.5%; QQQ when flat",
    "exit": "Rotate every 3 trading days",
    "position_size": "90% of cash",
    "eccentricity": "Cross-commodity macro signal with refined parameters. Gold/oil ratio as a regime thermometer.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    gld = data_fetcher.get_prices("GLD", start=start_date, end=end_date)
    uso = data_fetcher.get_prices("USO", start=start_date, end=end_date)
    xle = data_fetcher.get_prices("XLE", start=start_date, end=end_date)
    qqq = data_fetcher.get_prices("QQQ", start=start_date, end=end_date)

    for name, df in [("gld", gld), ("uso", uso), ("xle", xle), ("qqq", qqq)]:
        if isinstance(df.columns, pd.MultiIndex):
            if name == "gld":
                gld.columns = gld.columns.get_level_values(0)
            elif name == "uso":
                uso.columns = uso.columns.get_level_values(0)
            elif name == "xle":
                xle.columns = xle.columns.get_level_values(0)
            else:
                qqq.columns = qqq.columns.get_level_values(0)

    gld_close = gld["Close"]
    uso_close = uso["Close"]

    common = sorted(set(gld_close.index) & set(uso_close.index) & set(xle.index) & set(qqq.index))
    if len(common) < 12:
        return

    ratio = pd.Series(index=common, dtype=float)
    for day in common:
        g = float(gld_close.loc[day])
        o = float(uso_close.loc[day])
        if o > 0:
            ratio.loc[day] = g / o

    current_holding = None
    hold_counter = 0

    for i in range(7, len(common)):
        day = common[i]
        day_str = day.strftime("%Y-%m-%d") if hasattr(day, "strftime") else str(day)[:10]

        if current_holding:
            hold_counter += 1

        if hold_counter >= 3 or current_holding is None:
            lookback = common[i - 7]
            ratio_now = ratio.loc[day]
            ratio_then = ratio.loc[lookback]

            if pd.isna(ratio_now) or pd.isna(ratio_then) or ratio_then == 0:
                continue

            ratio_change = (ratio_now - ratio_then) / ratio_then

            if ratio_change > 0.015:
                target = "GLD"
            elif ratio_change < -0.015:
                target = "XLE"
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
