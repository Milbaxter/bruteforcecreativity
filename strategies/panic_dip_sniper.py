"""
Panic Dip Sniper
Buy healthy large-cap stocks when they get oversold during market fear events.
Exploit the mean reversion in panic-driven selloffs.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Panic Dip Sniper",
    "hypothesis": "When healthy large-caps (above 100-day MA) get oversold (RSI<25) during market fear (VIX>18) with volume surge, panic selling creates 3-5 day reversion opportunities.",
    "universe": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "JPM", "V", "UNH"],
    "entry": "RSI(5) < 25 + volume > 1.5x 20-day avg + price above 100-day MA + VIX > 18",
    "exit": "3 trading days or +3% take profit or -2% stop loss",
    "position_size": "25% of capital per position, max 2 positions at once",
    "eccentricity": "Multi-condition entry across 10 stocks with real-time volatility filter — too much monitoring for casual investors, too small for institutional quants",
}


def compute_rsi(series, period=5):
    """Compute RSI for a price series."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def run(data_fetcher, portfolio, start_date, end_date):
    tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "JPM", "V", "UNH"]

    # Fetch all price data
    price_data = {}
    for ticker in tickers:
        df = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if not df.empty:
            price_data[ticker] = df

    vix = data_fetcher.get_vix(start=start_date, end=end_date)

    if not price_data:
        return

    # Precompute signals for each ticker
    signals = {}
    for ticker, df in price_data.items():
        close = df["Close"]
        volume = df["Volume"]
        signals[ticker] = {
            "close": close,
            "rsi": compute_rsi(close, 5),
            "ma100": close.rolling(100).mean(),
            "vol_avg20": volume.rolling(20).mean(),
            "volume": volume,
        }

    # Use first ticker's index as reference trading days
    ref_ticker = next(iter(price_data))
    trading_days = price_data[ref_ticker].index.tolist()
    vix_aligned = vix.reindex(pd.DatetimeIndex(trading_days), method="ffill")

    # Track open positions: ticker -> (entry_price, entry_idx)
    open_positions = {}

    for i in range(105, len(trading_days)):
        date = trading_days[i]
        date_str = date.strftime("%Y-%m-%d")

        # Get VIX
        vix_val = float(vix_aligned.loc[date]) if date in vix_aligned.index and not pd.isna(vix_aligned.loc[date]) else 15

        # Manage exits first
        for ticker in list(open_positions.keys()):
            if ticker not in signals:
                continue
            entry_price, entry_idx = open_positions[ticker]
            current_price = float(signals[ticker]["close"].loc[date]) if date in signals[ticker]["close"].index else None
            if current_price is None:
                continue

            pct_change = (current_price - entry_price) / entry_price
            days_held = i - entry_idx

            # Exit: +3% take profit, -2% stop loss, or 3 days
            if pct_change >= 0.03 or pct_change <= -0.02 or days_held >= 3:
                portfolio.sell(ticker, all_shares=True, date=date_str)
                del open_positions[ticker]

        # Entry: only if we have room (max 2 positions)
        if len(open_positions) >= 2:
            continue

        # Check each ticker for entry signal
        for ticker in tickers:
            if ticker in open_positions:
                continue
            if ticker not in signals:
                continue
            if len(open_positions) >= 2:
                break

            sig = signals[ticker]
            if date not in sig["close"].index:
                continue

            rsi_val = float(sig["rsi"].loc[date]) if not pd.isna(sig["rsi"].loc[date]) else 50
            ma100_val = float(sig["ma100"].loc[date]) if not pd.isna(sig["ma100"].loc[date]) else 0
            price = float(sig["close"].loc[date])
            vol = float(sig["volume"].loc[date]) if not pd.isna(sig["volume"].loc[date]) else 0
            vol_avg = float(sig["vol_avg20"].loc[date]) if not pd.isna(sig["vol_avg20"].loc[date]) else 1

            # Entry conditions:
            # 1. RSI(5) < 25 (oversold)
            # 2. Volume > 1.5x 20-day average (volume surge)
            # 3. Price above 100-day MA (healthy stock)
            # 4. VIX > 18 (market fear)
            if rsi_val < 25 and vol > 1.5 * vol_avg and price > ma100_val and vix_val > 18:
                dollars = portfolio.cash * 0.25
                if dollars > 100:
                    result = portfolio.buy(ticker, dollars=dollars, date=date_str)
                    if result:
                        open_positions[ticker] = (result["exec_price"], i)
