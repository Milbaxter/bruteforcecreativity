"""
Fibonacci Retracement SOXX — buy SOXX when it pulls back to key Fibonacci levels.

Thesis: SOXX (semiconductors) is one of the most technically-traded ETFs because it's
dominated by technical/momentum traders. Fibonacci retracement levels (38.2%, 50%, 61.8%)
act as self-fulfilling support because so many traders watch them.

When SOXX makes a significant move up (>5% in 20 days) and then retraces to one of these
levels, the confluence of buy orders at these levels creates a bounce. Combined with:
- VIX < 28 (not a systemic crisis where technical levels break)
- Price above 50-day MA (long-term uptrend intact)

This is a technical analysis play that works because enough participants believe in it
to make it self-reinforcing at retail/small-cap scale.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Fib Retracement SOXX",
    "hypothesis": "SOXX Fibonacci retracement levels (38.2%, 50%) are self-fulfilling support. Buy when SOXX retraces to Fib level from prior rally + VIX < 28 + above 50d MA.",
    "universe": ["SOXX", "SPY"],
    "entry": "Buy SOXX when price hits 38.2% or 50% Fibonacci retracement of prior 20d rally AND VIX < 28 AND above 50d MA",
    "exit": "Sell after 5 days or +3%/-2% stop",
    "position_size": "85% of capital per trade",
    "eccentricity": "Self-fulfilling technical analysis on the most technically-traded sector ETF. Works because SOXX traders actively use Fibonacci levels.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    soxx = data_fetcher.get_prices("SOXX", start=start_date, end=end_date)
    vix = data_fetcher.get_vix(start=start_date, end=end_date)

    if soxx.empty or vix.empty:
        return

    soxx_close = soxx["Close"].dropna()
    soxx_close.index = pd.to_datetime(soxx_close.index)
    vix.index = pd.to_datetime(vix.index)

    common = soxx_close.index.intersection(vix.index)
    if len(common) < 55:
        return
    common = common.sort_values()

    soxx_c = soxx_close.loc[common]
    vix_c = vix.loc[common]
    ma50 = soxx_c.rolling(50).mean()

    in_trade = False
    entry_price = None
    days_held = 0

    for i in range(55, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        price = float(soxx_c.iloc[i])

        if in_trade:
            days_held += 1
            pnl_pct = (price - entry_price) / entry_price

            if days_held >= 5 or pnl_pct >= 0.03 or pnl_pct <= -0.02:
                portfolio.sell("SOXX", all_shares=True, date=date_str)
                in_trade = False
                entry_price = None
                days_held = 0

        elif not in_trade:
            # Find 20-day high and 20-day low in recent window
            window = soxx_c.iloc[max(0,i-20):i+1]
            high_20d = float(window.max())
            low_20d = float(window.min())
            swing = high_20d - low_20d

            if swing < high_20d * 0.03:  # Need at least 3% swing
                continue

            # Fibonacci levels from the 20d high
            fib_382 = high_20d - swing * 0.382
            fib_500 = high_20d - swing * 0.500
            fib_618 = high_20d - swing * 0.618

            vix_level = float(vix_c.iloc[i])
            ma50_val = float(ma50.iloc[i]) if pd.notna(ma50.iloc[i]) else 0

            # Check if price is near a Fibonacci level (within 0.5%)
            near_fib = False
            for fib_level in [fib_382, fib_500]:
                if abs(price - fib_level) / fib_level < 0.005:
                    near_fib = True
                    break

            # Also check if price is bouncing off fib (was below yesterday, above today)
            if not near_fib and i > 0:
                prev_price = float(soxx_c.iloc[i-1])
                for fib_level in [fib_382, fib_500]:
                    if prev_price < fib_level and price >= fib_level:
                        near_fib = True
                        break

            if near_fib and vix_level < 28 and price > ma50_val:
                result = portfolio.buy("SOXX", dollars=portfolio.cash * 0.85, date=date_str)
                if result:
                    in_trade = True
                    entry_price = price
                    days_held = 0

    if in_trade:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell("SOXX", all_shares=True, date=last_date)
