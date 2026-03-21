"""
Bullish Engulfing Scanner — scan ETFs daily for bullish engulfing with volume.

Thesis: A bullish engulfing candlestick (today's green body fully covers yesterday's
red body) is one of the most reliable short-term reversal patterns because it signals
a complete shift in intraday sentiment. When this occurs with above-average volume AND
above the 20-day MA (so we're buying in an uptrend context), the 3-day continuation
rate is historically 55-65%.

Scan 12 diverse ETFs every day. Buy the one with the strongest engulfing signal
(measured by the size of the engulfing candle relative to ATR). Hold 3 days.

Universe: QQQ, SOXX, XLF, XLE, XLV, XLI, EEM, IWM, TAN, XBI, KWEB, XHB
"""

import pandas as pd
import numpy as np

SCAN_UNIVERSE = ["QQQ", "SOXX", "XLF", "XLE", "XLV", "XLI", "EEM", "IWM", "TAN", "XBI", "KWEB", "XHB"]

STRATEGY = {
    "name": "Bullish Engulfing Scanner",
    "hypothesis": "Bullish engulfing candles + volume surge + uptrend = 55-65% chance of 3-day continuation. Scan 12 ETFs daily for the strongest signal.",
    "universe": SCAN_UNIVERSE + ["SPY"],
    "entry": "Buy ETF showing bullish engulfing (today green body covers yesterday red) + volume > 1.3x avg + price > 20d MA",
    "exit": "Sell after 3 days or +2.5%/-1.5% stop",
    "position_size": "80% of capital per trade",
    "eccentricity": "Daily candlestick pattern scanning across 12 ETFs with volume confirmation. Uses OHLC micro-structure, not just close prices.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    all_data = {}
    for ticker in SCAN_UNIVERSE:
        df = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
        if not df.empty and all(c in df.columns for c in ["Open", "High", "Low", "Close", "Volume"]):
            df.index = pd.to_datetime(df.index)
            all_data[ticker] = df

    if len(all_data) < 6:
        return

    # Common dates
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
            curr_price = float(all_data[trade_ticker]["Close"].loc[common[i]])
            pnl_pct = (curr_price - entry_price) / entry_price

            if days_held >= 3 or pnl_pct >= 0.025 or pnl_pct <= -0.015:
                portfolio.sell(trade_ticker, all_shares=True, date=date_str)
                in_trade = False
                trade_ticker = None
                entry_price = None
                days_held = 0

        elif not in_trade:
            best_ticker = None
            best_score = 0

            for ticker, df in all_data.items():
                if common[i] not in df.index or common[i-1] not in df.index:
                    continue

                # Yesterday's candle
                prev_open = float(df["Open"].loc[common[i-1]])
                prev_close = float(df["Close"].loc[common[i-1]])

                # Today's candle
                today_open = float(df["Open"].loc[common[i]])
                today_close = float(df["Close"].loc[common[i]])
                today_vol = float(df["Volume"].loc[common[i]])

                # Check: yesterday was red (bearish)
                if prev_close >= prev_open:
                    continue

                # Check: today is green (bullish) and engulfs yesterday
                if today_close <= today_open:
                    continue
                if today_open > prev_close or today_close < prev_open:
                    continue  # doesn't fully engulf

                # Volume check
                vol_window = df["Volume"].loc[common[max(0,i-20):i]]
                avg_vol = float(vol_window.mean()) if len(vol_window) > 0 else today_vol
                if avg_vol > 0 and today_vol / avg_vol < 1.3:
                    continue

                # 20-day MA check (uptrend)
                close_window = df["Close"].loc[common[max(0,i-20):i+1]]
                ma20 = float(close_window.mean())
                if today_close < ma20:
                    continue

                # Score: size of engulfing body relative to 10-day ATR
                atr_data = df.loc[common[max(0,i-10):i+1]]
                if len(atr_data) < 5:
                    continue
                atr = float((atr_data["High"] - atr_data["Low"]).mean())
                if atr <= 0:
                    continue

                body_size = abs(today_close - today_open)
                score = body_size / atr

                if score > best_score:
                    best_score = score
                    best_ticker = ticker

            if best_ticker:
                price = float(all_data[best_ticker]["Close"].loc[common[i]])
                result = portfolio.buy(best_ticker, dollars=portfolio.cash * 0.8, date=date_str)
                if result:
                    in_trade = True
                    trade_ticker = best_ticker
                    entry_price = price
                    days_held = 0

    if in_trade:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(trade_ticker, all_shares=True, date=last_date)
