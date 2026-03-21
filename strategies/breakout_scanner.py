"""
Breakout Scanner — buy the asset making the freshest 10-day high breakout.

Thesis: When an asset breaks to a new 10-day high, it signals fresh buying interest
that hasn't been seen in over two weeks. This breakout typically continues for 2-3
more days as: (1) stop orders above the old range get triggered, adding buying pressure,
(2) breakout-watching algorithms pile in, (3) short sellers cover.

Scan 5 diverse ETFs daily. When any makes a new 10-day high AND the close is in the
top 25% of the day's range (strong close, not a wick), buy it. When multiple break
out on the same day, buy the one with the highest percentage above the prior 10-day high.

Hold 3 days. -2% stop loss.
"""

import pandas as pd
import numpy as np

SCAN = ["QQQ", "SLV", "XLF", "SOXX", "IWM"]

STRATEGY = {
    "name": "Breakout Scanner",
    "hypothesis": "New 10-day highs signal fresh buying pressure. Buy the asset with the strongest breakout across 5 diverse ETFs. Hold 3 days.",
    "universe": SCAN + ["SPY"],
    "entry": "Buy asset making new 10d high with close in top 25% of day's range. Strongest breakout wins.",
    "exit": "Sell after 3 days or -2% stop",
    "position_size": "85% of capital per trade",
    "eccentricity": "Multi-asset breakout detection across diverse ETFs. Uses intraday bar structure (close position) to confirm strength of breakout.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    all_data = {}
    for ticker in SCAN:
        df = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
        if not df.empty and all(c in df.columns for c in ["Open", "High", "Low", "Close"]):
            df.index = pd.to_datetime(df.index)
            all_data[ticker] = df

    if len(all_data) < 3:
        return

    common = None
    for df in all_data.values():
        common = df.index if common is None else common.intersection(df.index)
    if common is None or len(common) < 15:
        return
    common = common.sort_values()

    in_trade = False
    trade_ticker = None
    entry_price = None
    days_held = 0

    for i in range(12, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")

        if in_trade:
            days_held += 1
            curr = float(all_data[trade_ticker]["Close"].loc[common[i]])
            pnl_pct = (curr - entry_price) / entry_price

            if days_held >= 3 or pnl_pct <= -0.02:
                portfolio.sell(trade_ticker, all_shares=True, date=date_str)
                in_trade = False
                trade_ticker = None
                entry_price = None
                days_held = 0

        elif not in_trade:
            best_ticker = None
            best_breakout = 0

            for ticker, df in all_data.items():
                if common[i] not in df.index:
                    continue

                close = float(df["Close"].loc[common[i]])
                high = float(df["High"].loc[common[i]])
                low = float(df["Low"].loc[common[i]])
                day_range = high - low
                if day_range <= 0:
                    continue

                # Close position in day's range (1.0 = closed at high)
                close_pos = (close - low) / day_range

                # 10-day high (excluding today)
                prev_10d = df["Close"].loc[common[max(0,i-10):i]]
                if len(prev_10d) < 5:
                    continue
                old_high = float(prev_10d.max())

                # Breakout: today's close > prior 10-day high AND strong close
                if close > old_high and close_pos > 0.75:
                    breakout_pct = (close - old_high) / old_high
                    if breakout_pct > best_breakout:
                        best_breakout = breakout_pct
                        best_ticker = ticker

            if best_ticker:
                price = float(all_data[best_ticker]["Close"].loc[common[i]])
                result = portfolio.buy(best_ticker, dollars=portfolio.cash * 0.85, date=date_str)
                if result:
                    in_trade = True
                    trade_ticker = best_ticker
                    entry_price = price
                    days_held = 0

    if in_trade:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(trade_ticker, all_shares=True, date=last_date)
