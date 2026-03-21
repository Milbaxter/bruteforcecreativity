"""
Treasury Yield Regime Switch: Use 10-year Treasury yield direction to switch
between financials (XLF) and tech (XLK).

Thesis: Rising yields benefit banks (wider net interest margins) and hurt
growth/tech (higher discount rates). Falling yields do the opposite.
By tracking the 5-day yield trend, we can capture sector rotation flows
as they happen.

Added twist: include GLD as a third option when yields are flat (range-bound).
"""

import pandas as pd

STRATEGY = {
    "name": "Yield Regime Switch",
    "hypothesis": "10Y yield direction drives sector rotation: rising yields favor financials, falling yields favor tech. We ride this rotation in 3-day bursts.",
    "universe": ["XLF", "XLK", "GLD", "SPY"],
    "entry": "Buy XLF when 5-day yield change is positive; buy XLK when negative; buy GLD when flat",
    "exit": "Rotate every 3 trading days based on updated yield trend",
    "position_size": "90% of cash in the regime winner",
    "eccentricity": "Macro-driven sector rotation at daytrader speed. Institutional macro funds rotate monthly. We rotate every 3 days based on yield momentum.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Get 10Y yield proxy via ^TNX
    tnx = data_fetcher.get_prices("^TNX", start=start_date, end=end_date)
    if isinstance(tnx.columns, pd.MultiIndex):
        tnx.columns = tnx.columns.get_level_values(0)

    if tnx.empty:
        return

    tnx_close = tnx["Close"]

    # Get sector ETFs
    xlf = data_fetcher.get_prices("XLF", start=start_date, end=end_date)
    xlk = data_fetcher.get_prices("XLK", start=start_date, end=end_date)
    gld = data_fetcher.get_prices("GLD", start=start_date, end=end_date)

    for name, df in [("xlf", xlf), ("xlk", xlk), ("gld", gld)]:
        if isinstance(df.columns, pd.MultiIndex):
            if name == "xlf":
                xlf.columns = xlf.columns.get_level_values(0)
            elif name == "xlk":
                xlk.columns = xlk.columns.get_level_values(0)
            else:
                gld.columns = gld.columns.get_level_values(0)

    # Common trading days across all instruments
    all_sets = [set(tnx_close.index), set(xlf.index), set(xlk.index), set(gld.index)]
    common = sorted(set.intersection(*all_sets))

    if len(common) < 10:
        return

    current_holding = None
    hold_counter = 0
    rotation_period = 3

    for i in range(5, len(common)):
        day = common[i]
        day_str = day.strftime("%Y-%m-%d") if hasattr(day, "strftime") else str(day)[:10]

        if current_holding:
            hold_counter += 1

        if hold_counter >= rotation_period or current_holding is None:
            # 5-day yield change
            lookback = common[i - 5]
            yield_now = float(tnx_close.loc[day])
            yield_then = float(tnx_close.loc[lookback])
            yield_change = yield_now - yield_then  # In percentage points

            # Determine target
            if yield_change > 0.05:  # Yields rising meaningfully
                target = "XLF"
            elif yield_change < -0.05:  # Yields falling meaningfully
                target = "XLK"
            else:  # Yields flat
                target = "GLD"

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
