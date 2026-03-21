"""
Oil Gold Macro Switch: Use the gold-to-oil ratio (GLD/USO) as a macro regime
indicator. When gold is strengthening vs oil, it signals risk aversion —
buy GLD. When oil is strengthening vs gold, it signals growth/inflation —
buy XLE (energy stocks, not just oil).

The twist: when neither is dominant (ratio is flat), buy QQQ (tech rally).
"""

import pandas as pd

STRATEGY = {
    "name": "Oil Gold Macro Switch",
    "hypothesis": "The gold-to-oil ratio is a macro thermometer. Rising ratio = fear (buy gold). Falling ratio = growth (buy energy). Flat = tech rally.",
    "universe": ["GLD", "USO", "XLE", "QQQ"],
    "entry": "Buy GLD when gold/oil ratio is rising; buy XLE when falling; buy QQQ when flat",
    "exit": "Rotate every 3 trading days based on updated ratio trend",
    "position_size": "90% of cash",
    "eccentricity": "Cross-commodity ratio as a macro signal for equity sector selection. Too indirect for commodity funds, too weird for equity funds.",
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
    if len(common) < 10:
        return

    # Compute gold/oil ratio
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
            # 5-day change in ratio
            lookback = common[i - 5]
            ratio_now = ratio.loc[day]
            ratio_then = ratio.loc[lookback]

            if pd.isna(ratio_now) or pd.isna(ratio_then) or ratio_then == 0:
                continue

            ratio_change = (ratio_now - ratio_then) / ratio_then

            if ratio_change > 0.02:  # Gold strengthening vs oil
                target = "GLD"
            elif ratio_change < -0.02:  # Oil strengthening vs gold
                target = "XLE"
            else:  # Flat
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
