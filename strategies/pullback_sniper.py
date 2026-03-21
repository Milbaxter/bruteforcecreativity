"""
Pullback Sniper: Buy QQQ aggressively when it pulls back 2%+ from its 10-day high.
Sell when it recovers to within 0.5% of the high, or after 7 days, or at -4% stop.

Thesis: In a bull market, every pullback gets bought. "Buy the dip" is the
dominant reflex of 2024-2025. The trick is to be systematic about it:
- Wait for a meaningful dip (2% from 10-day high)
- Enter with high conviction (90% of cash)
- Exit when the dip has been bought (price recovers near high)

This is how retail traders think, but we're systematic about it.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Pullback Sniper",
    "hypothesis": "In a bull market, QQQ pullbacks of 2%+ from recent highs get bought aggressively within 3-7 days. Being systematic about buying these dips captures the reflex.",
    "universe": ["QQQ"],
    "entry": "Buy QQQ when price is 2%+ below its 10-day rolling high",
    "exit": "Sell when price recovers to within 0.5% of 10-day high, or after 7 days, or at -4% stop loss",
    "position_size": "90% of cash",
    "eccentricity": "Systematized 'buy the dip' — too simple for quant funds, too aggressive for risk-managed portfolios. Works because retail FOMO is a reliable force in bull markets.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    qqq = data_fetcher.get_prices("QQQ", start=start_date, end=end_date)

    if isinstance(qqq.columns, pd.MultiIndex):
        qqq.columns = qqq.columns.get_level_values(0)

    if qqq.empty:
        return

    close = qqq["Close"]
    trading_days = sorted(close.index)

    if len(trading_days) < 15:
        return

    in_position = False
    entry_price = None
    days_held = 0

    for i in range(10, len(trading_days)):
        day = trading_days[i]
        day_str = day.strftime("%Y-%m-%d") if hasattr(day, "strftime") else str(day)[:10]
        current_price = float(close.loc[day])

        # 10-day rolling high
        lookback_prices = [float(close.loc[trading_days[j]]) for j in range(i - 10, i + 1)]
        rolling_high = max(lookback_prices)

        drawdown = (current_price - rolling_high) / rolling_high

        if in_position:
            days_held += 1
            pct_from_entry = (current_price - entry_price) / entry_price

            # Exit conditions:
            # 1. Price recovered to within 0.5% of rolling high
            # 2. After 7 trading days
            # 3. Stop loss at -4%
            if drawdown > -0.005 or days_held >= 7 or pct_from_entry <= -0.04:
                portfolio.sell("QQQ", all_shares=True, date=day_str)
                in_position = False
                entry_price = None
                days_held = 0
        else:
            # Entry: price is 2%+ below 10-day high
            if drawdown <= -0.02:
                result = portfolio.buy("QQQ", dollars=portfolio.cash * 0.90, date=day_str)
                if result:
                    in_position = True
                    entry_price = current_price
                    days_held = 0

    # Close remaining
    if in_position and trading_days:
        last = trading_days[-1].strftime("%Y-%m-%d")
        portfolio.sell("QQQ", all_shares=True, date=last)
