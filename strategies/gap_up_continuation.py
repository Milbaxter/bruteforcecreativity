"""
Gap-Up Volume Continuation — buy mega-cap ETFs on strong gap-ups with volume surge.

Thesis: When a major ETF gaps up >1% (open > prev close) with above-average volume,
it signals genuine buying pressure, not just noise. For liquid ETFs (QQQ, SOXX, XLF),
gap-ups with volume confirmation tend to continue for 2-3 more days because:
(1) institutional buying takes multiple days to execute
(2) gap-ups attract momentum chasers who add fuel
(3) short covering adds additional buying pressure

Three signals:
1. Gap-up: Open > previous Close by > 1%
2. Volume surge: today's volume > 1.5x 20-day average
3. Trend support: price above 10-day MA (gap confirms existing uptrend, not a dead cat)

Buy the gapping ETF, sell after 3 days or at targets.
"""

import pandas as pd
import numpy as np

UNIVERSE = ["QQQ", "SOXX", "XLF", "XLI", "XLK", "XLE"]

STRATEGY = {
    "name": "Gap Up Continuation",
    "hypothesis": "ETF gap-ups > 1% with volume surge signal institutional buying that continues for 2-3 days. Buy on confirmed gap-up with volume + trend support.",
    "universe": UNIVERSE + ["SPY"],
    "entry": "Buy ETF when open > prev close by > 1% AND volume > 1.5x 20d avg AND price > 10d MA",
    "exit": "Sell after 3 days or +2.5%/-1.5% stop",
    "position_size": "80% of capital per trade",
    "eccentricity": "Intraday gap structure + volume confirmation across multiple liquid ETFs. Uses open-to-prev-close relationship, not just close-to-close.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    all_data = {}
    for ticker in UNIVERSE:
        df = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
        if not df.empty and all(c in df.columns for c in ["Open", "Close", "Volume"]):
            df.index = pd.to_datetime(df.index)
            all_data[ticker] = df

    if len(all_data) < 3:
        return

    # Find common dates
    common = None
    for df in all_data.values():
        common = df.index if common is None else common.intersection(df.index)
    if common is None or len(common) < 25:
        return
    common = common.sort_values()

    in_trade = False
    trade_ticker = None
    entry_price = None
    days_held = 0

    for i in range(25, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")

        if in_trade:
            days_held += 1
            current_price = float(all_data[trade_ticker]["Close"].loc[common[i]])
            pnl_pct = (current_price - entry_price) / entry_price

            if days_held >= 3 or pnl_pct >= 0.025 or pnl_pct <= -0.015:
                portfolio.sell(trade_ticker, all_shares=True, date=date_str)
                in_trade = False
                trade_ticker = None
                entry_price = None
                days_held = 0

        elif not in_trade:
            # Check all tickers for gap-up + volume + trend
            best_gap = None
            best_gap_pct = 0

            for ticker, df in all_data.items():
                if common[i] not in df.index or common[i-1] not in df.index:
                    continue

                prev_close = float(df["Close"].loc[common[i-1]])
                today_open = float(df["Open"].loc[common[i]])
                today_close = float(df["Close"].loc[common[i]])
                today_vol = float(df["Volume"].loc[common[i]])

                gap_pct = (today_open - prev_close) / prev_close

                # 20-day average volume
                vol_window = df["Volume"].loc[common[max(0,i-20):i]]
                avg_vol = float(vol_window.mean()) if len(vol_window) > 0 else today_vol
                vol_ratio = today_vol / avg_vol if avg_vol > 0 else 1

                # 10-day MA
                close_window = df["Close"].loc[common[max(0,i-10):i+1]]
                ma10 = float(close_window.mean()) if len(close_window) > 0 else today_close

                # Gap-up + volume + trend
                if gap_pct > 0.01 and vol_ratio > 1.5 and today_close > ma10:
                    if gap_pct > best_gap_pct:
                        best_gap = ticker
                        best_gap_pct = gap_pct

            if best_gap:
                price = float(all_data[best_gap]["Close"].loc[common[i]])
                result = portfolio.buy(best_gap, dollars=portfolio.cash * 0.8, date=date_str)
                if result:
                    in_trade = True
                    trade_ticker = best_gap
                    entry_price = price
                    days_held = 0

    if in_trade:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(trade_ticker, all_shares=True, date=last_date)
