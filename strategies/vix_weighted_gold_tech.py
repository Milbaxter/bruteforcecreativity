"""
VIX-Weighted Gold/Tech Switch: Use VIX level as a regime indicator.
High VIX = fear = buy GLD. Low VIX = greed = buy QQQ.
Medium VIX = buy XLE (energy as a middle ground).

Thesis: VIX is the market's fear gauge. When VIX is elevated (>20),
gold outperforms as a safe haven. When VIX is low (<16), tech rallies
hardest. In between, energy captures the uncertain middle.

The rotation happens every 3 days to keep holding periods short.
"""

import pandas as pd

STRATEGY = {
    "name": "VIX-Weighted Gold Tech",
    "hypothesis": "VIX level directly predicts which asset class outperforms. High VIX favors gold, low VIX favors tech, medium favors energy. Simple but robust regime signal.",
    "universe": ["GLD", "QQQ", "XLE"],
    "entry": "Buy GLD when VIX >22; QQQ when VIX <17; XLE when 17-22",
    "exit": "Rotate every 3 trading days based on current VIX level",
    "position_size": "90% of cash",
    "eccentricity": "Using VIX as a direct asset allocator. Too simplistic for quant models, too fast for macro funds. But VIX regimes are remarkably predictive of asset class returns.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    vix = data_fetcher.get_vix(start=start_date, end=end_date)

    gld = data_fetcher.get_prices("GLD", start=start_date, end=end_date)
    qqq = data_fetcher.get_prices("QQQ", start=start_date, end=end_date)
    xle = data_fetcher.get_prices("XLE", start=start_date, end=end_date)

    for name, df in [("gld", gld), ("qqq", qqq), ("xle", xle)]:
        if isinstance(df.columns, pd.MultiIndex):
            if name == "gld":
                gld.columns = gld.columns.get_level_values(0)
            elif name == "qqq":
                qqq.columns = qqq.columns.get_level_values(0)
            else:
                xle.columns = xle.columns.get_level_values(0)

    if vix.empty:
        return

    common = sorted(
        set(vix.index) & set(gld.index) & set(qqq.index) & set(xle.index)
    )
    if len(common) < 5:
        return

    current_holding = None
    hold_counter = 0

    for i in range(len(common)):
        day = common[i]
        day_str = day.strftime("%Y-%m-%d") if hasattr(day, "strftime") else str(day)[:10]

        if current_holding:
            hold_counter += 1

        if hold_counter >= 3 or current_holding is None:
            current_vix = float(vix.loc[day])

            if current_vix > 22:
                target = "GLD"
            elif current_vix < 17:
                target = "QQQ"
            else:
                target = "XLE"

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
