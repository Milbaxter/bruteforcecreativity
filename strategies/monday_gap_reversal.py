"""
Monday Gap Reversal
Buy QQQ when Monday opens lower than Friday's close (gap down), with VIX and trend filters.
Monday gap-downs in uptrending markets tend to fill within 2-3 days.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Monday Gap Reversal",
    "hypothesis": "Monday gap-downs in uptrending markets are driven by weekend fear and thin overnight liquidity. With VIX elevated and price above 50-day MA, these gaps fill 60-70% of the time within 2-3 days.",
    "universe": ["QQQ", "SPY"],
    "entry": "Monday open < Friday close by > 0.3% + VIX > 16 + QQQ above 50-day MA",
    "exit": "Close by Wednesday (2 trading days) or at +1.5% take profit or -1.5% stop loss",
    "position_size": "90% of capital per trade",
    "eccentricity": "Calendar anomaly (day-of-week effect) combined with behavioral fear signal — the kind of edge too small and sporadic for systematic institutional funds to model",
}


def run(data_fetcher, portfolio, start_date, end_date):
    prices_qqq = data_fetcher.get_prices("QQQ", start=start_date, end=end_date)
    prices_spy = data_fetcher.get_prices("SPY", start=start_date, end=end_date)
    vix = data_fetcher.get_vix(start=start_date, end=end_date)

    for df in [prices_qqq, prices_spy]:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

    if prices_qqq.empty:
        return

    qqq_close = prices_qqq["Close"]
    qqq_open = prices_qqq["Open"]
    qqq_ma50 = qqq_close.rolling(50).mean()

    trading_days = prices_qqq.index.tolist()
    vix_aligned = vix.reindex(pd.DatetimeIndex(trading_days), method="ffill")

    in_position = False
    entry_price = None
    entry_idx = None
    entry_ticker = None

    for i in range(55, len(trading_days)):
        date = trading_days[i]
        date_str = date.strftime("%Y-%m-%d")

        # Exit management
        if in_position:
            current = float(qqq_close.loc[date]) if entry_ticker == "QQQ" else float(prices_spy["Close"].loc[date])
            pct = (current - entry_price) / entry_price
            days_held = i - entry_idx

            # Exit: +1.5% profit, -1.5% stop, or 2 trading days
            if pct >= 0.015 or pct <= -0.015 or days_held >= 2:
                portfolio.sell(entry_ticker, all_shares=True, date=date_str)
                in_position = False
                entry_price = None
                entry_idx = None
                entry_ticker = None
            continue

        # Only enter on Mondays
        if date.weekday() != 0:  # 0 = Monday
            continue

        # Find previous Friday (last trading day before Monday)
        prev_idx = i - 1
        while prev_idx >= 0 and trading_days[prev_idx].weekday() > 4:
            prev_idx -= 1
        if prev_idx < 0:
            continue

        friday = trading_days[prev_idx]
        friday_close = float(qqq_close.loc[friday])
        monday_open = float(qqq_open.loc[date])

        # Gap calculation
        gap_pct = (monday_open - friday_close) / friday_close

        # VIX
        vix_val = float(vix_aligned.loc[date]) if date in vix_aligned.index and not pd.isna(vix_aligned.loc[date]) else 15

        # MA50
        ma50 = float(qqq_ma50.loc[date]) if not pd.isna(qqq_ma50.loc[date]) else 0
        qqq_price = float(qqq_close.loc[date])

        # Entry: gap down > 0.3% + VIX > 16 + above 50-day MA
        if gap_pct < -0.003 and vix_val > 16 and qqq_price > ma50:
            # Buy QQQ
            dollars = portfolio.cash * 0.90
            result = portfolio.buy("QQQ", dollars=dollars, date=date_str)
            if result:
                in_position = True
                entry_price = result["exec_price"]
                entry_idx = i
                entry_ticker = "QQQ"
        # Also try SPY gap-downs when QQQ doesn't gap
        elif gap_pct < -0.005 and vix_val > 18:
            # Larger gap without trend filter — buy SPY as broader market bounce
            dollars = portfolio.cash * 0.90
            result = portfolio.buy("SPY", dollars=dollars, date=date_str)
            if result:
                in_position = True
                entry_price = result["exec_price"]
                entry_idx = i
                entry_ticker = "SPY"
