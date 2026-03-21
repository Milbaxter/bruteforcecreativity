"""
FOMC Day Drift: Buy SPY 1 day before each FOMC announcement, sell 1 day after.

The pre-FOMC drift is one of the most well-documented anomalies in finance.
Markets tend to drift upward in the 24 hours before FOMC announcements,
regardless of what the Fed actually does. This is attributed to short covering,
positioning, and reduced selling pressure ahead of uncertainty resolution.

We also trade CPI and Jobs report days with the same logic — macro event
resolution tends to be bullish for equities (the uncertainty discount gets removed).
"""

import pandas as pd

STRATEGY = {
    "name": "FOMC Day Drift",
    "hypothesis": "Markets drift up before FOMC/CPI/Jobs releases as uncertainty premium gets priced out. The resolution of uncertainty itself is bullish, regardless of outcome.",
    "universe": ["SPY", "QQQ"],
    "entry": "Buy SPY and QQQ 1 trading day before FOMC/CPI/Jobs release",
    "exit": "Sell 1 trading day after the event",
    "position_size": "40% of cash in SPY, 40% in QQQ per event",
    "eccentricity": "Pure calendar anomaly. Big funds can't allocate based on Fed meeting schedules — it looks too simplistic for their LPs. But the drift is real and has persisted for decades.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Get economic calendar
    econ_cal = data_fetcher.get_economic_calendar()

    if econ_cal.empty:
        return

    # Get all FOMC, CPI, and Jobs dates
    event_dates = econ_cal["date"].tolist()

    # Get price data
    spy = data_fetcher.get_prices("SPY", start=start_date, end=end_date)
    if isinstance(spy.columns, pd.MultiIndex):
        spy.columns = spy.columns.get_level_values(0)

    trading_days = sorted(spy.index)
    trading_day_strs = [d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10] for d in trading_days]

    # Normalize event dates to strings
    event_date_strs = set()
    for d in event_dates:
        if hasattr(d, "strftime"):
            event_date_strs.add(d.strftime("%Y-%m-%d"))
        else:
            event_date_strs.add(str(d)[:10])

    in_position = False
    exit_after_date = None

    for i, day in enumerate(trading_days):
        day_str = trading_day_strs[i]

        if in_position:
            # Check if we should exit (1 day after event)
            if day_str >= exit_after_date:
                portfolio.sell("SPY", all_shares=True, date=day_str)
                portfolio.sell("QQQ", all_shares=True, date=day_str)
                in_position = False
                exit_after_date = None
            continue

        # Look ahead: is the next trading day an event day?
        if i + 1 < len(trading_days):
            next_day_str = trading_day_strs[i + 1]
            if next_day_str in event_date_strs:
                # Buy today (day before event)
                cash = portfolio.cash
                if cash < 200:
                    continue

                r1 = portfolio.buy("SPY", dollars=cash * 0.40, date=day_str)
                r2 = portfolio.buy("QQQ", dollars=portfolio.cash * 0.60, date=day_str)

                if r1 or r2:
                    in_position = True
                    # Set exit: 1 trading day after the event
                    if i + 2 < len(trading_days):
                        exit_after_date = trading_day_strs[i + 2]
                    else:
                        exit_after_date = trading_day_strs[-1]

        # Also check if TODAY is an event day and we missed the day-before entry
        if day_str in event_date_strs and not in_position:
            cash = portfolio.cash
            if cash < 200:
                continue

            r1 = portfolio.buy("SPY", dollars=cash * 0.40, date=day_str)
            r2 = portfolio.buy("QQQ", dollars=portfolio.cash * 0.60, date=day_str)

            if r1 or r2:
                in_position = True
                if i + 1 < len(trading_days):
                    exit_after_date = trading_day_strs[i + 1]
                else:
                    exit_after_date = trading_day_strs[-1]

    # Close remaining
    if in_position and trading_days:
        last = trading_day_strs[-1]
        portfolio.sell("SPY", all_shares=True, date=last)
        portfolio.sell("QQQ", all_shares=True, date=last)
