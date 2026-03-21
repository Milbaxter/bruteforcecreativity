"""
Consecutive Up Days Momentum: When QQQ or SPY has 3+ consecutive up days,
go all-in on the one showing more strength. Exit on first down day or after 5 days.

Thesis: In bull markets, streaks beget streaks. After 3 consecutive up days,
there's institutional FOMO and systematic trend-following algos that pile in.
The momentum typically persists for 1-3 more days before exhaustion.

The key insight: we alternate between QQQ and SPY based on which is showing
more relative strength during the streak, concentrating in the winner.
"""

import pandas as pd

STRATEGY = {
    "name": "Consecutive Up Days Momentum",
    "hypothesis": "3+ consecutive up days trigger institutional FOMO and trend-following algos. The streak typically extends 1-3 more days. Concentrating in the stronger index amplifies returns.",
    "universe": ["SPY", "QQQ"],
    "entry": "Buy QQQ or SPY (whichever has stronger 3-day run) after 3 consecutive up days",
    "exit": "Sell on first down day or after 5 trading days max",
    "position_size": "90% of cash, concentrated in the winning index",
    "eccentricity": "Pure streak-riding. Institutional risk managers hate concentrated momentum bets. Too simple for quant models, too aggressive for fundamental funds.",
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
    if len(common) < 5:
        return

    in_position = False
    current_ticker = None
    days_held = 0

    for i in range(3, len(common)):
        day = common[i]
        day_str = day.strftime("%Y-%m-%d") if hasattr(day, "strftime") else str(day)[:10]

        spy_today = float(spy_close.loc[day])
        qqq_today = float(qqq_close.loc[day])

        if in_position:
            days_held += 1

            # Exit on down day for the held ticker
            prev_day = common[i - 1]
            if current_ticker == "SPY":
                prev_price = float(spy_close.loc[prev_day])
                today_price = spy_today
            else:
                prev_price = float(qqq_close.loc[prev_day])
                today_price = qqq_today

            day_return = (today_price - prev_price) / prev_price

            # Exit: first down day or 5 days max
            if day_return < 0 or days_held >= 5:
                portfolio.sell(current_ticker, all_shares=True, date=day_str)
                in_position = False
                current_ticker = None
                days_held = 0
        else:
            # Check for 3 consecutive up days in SPY
            spy_streak = True
            qqq_streak = True
            spy_3d_ret = 0
            qqq_3d_ret = 0

            for j in range(1, 4):
                d1 = common[i - j]
                d0 = common[i - j + 1] if (i - j + 1) < len(common) else common[i]
                # Actually let's check i-3 to i
                pass

            # Simpler: check last 3 daily returns
            returns_spy = []
            returns_qqq = []
            for j in range(3):
                idx = i - 2 + j  # i-2, i-1, i
                if idx > 0:
                    prev = common[idx - 1]
                    cur = common[idx]
                    s_ret = (float(spy_close.loc[cur]) - float(spy_close.loc[prev])) / float(spy_close.loc[prev])
                    q_ret = (float(qqq_close.loc[cur]) - float(qqq_close.loc[prev])) / float(qqq_close.loc[prev])
                    returns_spy.append(s_ret)
                    returns_qqq.append(q_ret)

            if len(returns_spy) < 3:
                continue

            spy_all_up = all(r > 0 for r in returns_spy)
            qqq_all_up = all(r > 0 for r in returns_qqq)

            if spy_all_up or qqq_all_up:
                # Pick the stronger one over the 3-day period
                spy_3d = sum(returns_spy)
                qqq_3d = sum(returns_qqq)

                if qqq_all_up and (not spy_all_up or qqq_3d > spy_3d):
                    pick = "QQQ"
                elif spy_all_up:
                    pick = "SPY"
                else:
                    continue

                result = portfolio.buy(pick, dollars=portfolio.cash * 0.90, date=day_str)
                if result:
                    in_position = True
                    current_ticker = pick
                    days_held = 0

    # Close remaining
    if in_position and common:
        last = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(current_ticker, all_shares=True, date=last)
