"""
Gold Silver Rotation: Rotate between GLD and SLV based on relative momentum.
Silver is more volatile than gold, so when precious metals are strong,
silver outperforms. Switch to GLD when the trend weakens (gold is safer).

Also rotates into QQQ when both metals are losing momentum (risk-on).
"""

import pandas as pd

STRATEGY = {
    "name": "Gold Silver Rotation",
    "hypothesis": "Silver outperforms gold in strong precious metal bull trends due to higher beta. When metals weaken, QQQ captures the risk-on rotation. 3-day rotations catch shifts early.",
    "universe": ["GLD", "SLV", "QQQ"],
    "entry": "Buy SLV when silver 5-day momentum > gold; buy GLD when gold > silver; buy QQQ when both negative",
    "exit": "Rotate every 3 trading days",
    "position_size": "90% of cash",
    "eccentricity": "Precious metals beta rotation is a niche trade. Adding QQQ as the risk-on escape hatch makes it a three-regime model no fund would implement.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    gld = data_fetcher.get_prices("GLD", start=start_date, end=end_date)
    slv = data_fetcher.get_prices("SLV", start=start_date, end=end_date)
    qqq = data_fetcher.get_prices("QQQ", start=start_date, end=end_date)

    for name, df in [("gld", gld), ("slv", slv), ("qqq", qqq)]:
        if isinstance(df.columns, pd.MultiIndex):
            if name == "gld":
                gld.columns = gld.columns.get_level_values(0)
            elif name == "slv":
                slv.columns = slv.columns.get_level_values(0)
            else:
                qqq.columns = qqq.columns.get_level_values(0)

    gld_close = gld["Close"]
    slv_close = slv["Close"]
    qqq_close = qqq["Close"]

    common = sorted(set(gld_close.index) & set(slv_close.index) & set(qqq_close.index))
    if len(common) < 10:
        return

    current_holding = None
    hold_counter = 0

    for i in range(5, len(common)):
        day = common[i]
        day_str = day.strftime("%Y-%m-%d") if hasattr(day, "strftime") else str(day)[:10]

        if current_holding:
            hold_counter += 1

        if hold_counter >= 3 or current_holding is None:
            lookback = common[i - 5]

            gld_ret = (float(gld_close.loc[day]) - float(gld_close.loc[lookback])) / float(gld_close.loc[lookback])
            slv_ret = (float(slv_close.loc[day]) - float(slv_close.loc[lookback])) / float(slv_close.loc[lookback])
            qqq_ret = (float(qqq_close.loc[day]) - float(qqq_close.loc[lookback])) / float(qqq_close.loc[lookback])

            # Regime logic
            if gld_ret < 0 and slv_ret < 0:
                target = "QQQ"  # Both metals down = risk-on
            elif slv_ret > gld_ret:
                target = "SLV"  # Silver outperforming = strong metals trend
            else:
                target = "GLD"  # Gold outperforming = defensive metals

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
