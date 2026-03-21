"""
Extreme Range Reversal — buy SPY when daily range is extreme and close is near the low.

Thesis: When SPY's intraday range (high-low / close) exceeds 2% AND the close is in
the bottom 25% of the daily range, it signals capitulation selling. The next 1-3 days
tend to see a reversal bounce as the panic subsides. Combined with: volume must be
above average (confirms real institutional selling, not thin-market noise) AND the
5-day RSI < 40 (confirming oversold condition).

Three signals:
1. Daily range (H-L)/Close > 2% (extreme intraday volatility)
2. Close in bottom 25% of day's range ((Close-Low)/(High-Low) < 0.25)
3. Volume > 1.2x 20-day average (real selling pressure, not thin market)

Buy SPY at close, sell after 2-3 days or at targets.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Extreme Range Reversal",
    "hypothesis": "SPY wide range day + close near low + high volume = capitulation. Bounce follows within 1-3 days.",
    "universe": ["SPY"],
    "entry": "Buy SPY when daily range > 2% AND close in bottom 25% of range AND volume > 1.2x 20d avg",
    "exit": "Sell after 3 days or +2%/-1.5% stop",
    "position_size": "90% of capital per trade",
    "eccentricity": "Intraday price structure (range position) as capitulation signal. Uses daily bar micro-structure rather than just close-to-close returns.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    spy = data_fetcher.get_prices("SPY", start=start_date, end=end_date)

    if spy.empty:
        return

    # Need OHLCV
    spy.index = pd.to_datetime(spy.index)
    if not all(c in spy.columns for c in ["Open", "High", "Low", "Close", "Volume"]):
        return

    spy_high = spy["High"]
    spy_low = spy["Low"]
    spy_close = spy["Close"]
    spy_open = spy["Open"]
    spy_volume = spy["Volume"]

    # Daily range as % of close
    daily_range_pct = (spy_high - spy_low) / spy_close
    # Close position within range (0 = closed at low, 1 = closed at high)
    range_span = spy_high - spy_low
    close_position = (spy_close - spy_low) / range_span.replace(0, np.nan)
    # Volume ratio vs 20-day average
    vol_avg20 = spy_volume.rolling(20).mean()
    vol_ratio = spy_volume / vol_avg20

    in_trade = False
    entry_price = None
    days_held = 0

    for i in range(25, len(spy)):
        date_str = spy.index[i].strftime("%Y-%m-%d")
        price = float(spy_close.iloc[i])

        if in_trade:
            days_held += 1
            pnl_pct = (price - entry_price) / entry_price

            if days_held >= 3 or pnl_pct >= 0.02 or pnl_pct <= -0.015:
                portfolio.sell("SPY", all_shares=True, date=date_str)
                in_trade = False
                entry_price = None
                days_held = 0

        elif not in_trade:
            dr = float(daily_range_pct.iloc[i]) if pd.notna(daily_range_pct.iloc[i]) else 0
            cp = float(close_position.iloc[i]) if pd.notna(close_position.iloc[i]) else 0.5
            vr = float(vol_ratio.iloc[i]) if pd.notna(vol_ratio.iloc[i]) else 1.0

            # Capitulation: big range + close near low + high volume
            if dr > 0.02 and cp < 0.25 and vr > 1.2:
                result = portfolio.buy("SPY", dollars=portfolio.cash * 0.9, date=date_str)
                if result:
                    in_trade = True
                    entry_price = price
                    days_held = 0

    if in_trade:
        last_date = spy.index[-1].strftime("%Y-%m-%d")
        portfolio.sell("SPY", all_shares=True, date=last_date)
