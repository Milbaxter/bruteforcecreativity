"""
VIX Spike Mean Reversion: Buy SPY when VIX spikes above its upper Bollinger Band
(2 standard deviations above 20-day mean), sell when VIX drops back below the mean.

The thesis: retail panic creates short-term overselling. When VIX spikes sharply,
markets tend to snap back within 1-5 days. Big funds can't react fast enough
to these quick mean-reversion windows, and their risk committees won't let them
"buy the panic" aggressively.
"""

import pandas as pd

STRATEGY = {
    "name": "VIX Spike Mean Reversion",
    "hypothesis": "When VIX spikes above its 20-day upper Bollinger Band, retail panic has oversold the market. SPY tends to snap back within 1-5 days as fear normalizes.",
    "universe": ["SPY"],
    "entry": "Buy SPY when VIX closes above 20-day MA + 2 standard deviations",
    "exit": "Sell when VIX drops back below its 20-day MA, or after 5 trading days (whichever first). Stop loss at -3%.",
    "position_size": "50% of available cash per trade",
    "eccentricity": "Exploits retail panic selling windows too short for institutional risk committees to approve. The 1-5 day hold is too fast for most fund mandates.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Fetch VIX and SPY data
    vix = data_fetcher.get_vix(start=start_date, end=end_date)
    spy = data_fetcher.get_prices("SPY", start=start_date, end=end_date)

    if isinstance(spy.columns, pd.MultiIndex):
        spy_close = spy[("Close", "SPY")]
    else:
        spy_close = spy["Close"]

    if vix.empty or spy_close.empty:
        return

    # Compute VIX Bollinger Bands (20-day)
    vix_ma = vix.rolling(20).mean()
    vix_std = vix.rolling(20).std()
    vix_upper = vix_ma + 2 * vix_std

    # Align all series
    dates = sorted(set(vix.index) & set(spy_close.index) & set(vix_ma.dropna().index))

    in_position = False
    entry_date = None
    entry_price = None
    days_held = 0

    for i, date in enumerate(dates):
        date_str = date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)[:10]
        current_vix = vix.loc[date]
        current_spy = spy_close.loc[date]
        current_ma = vix_ma.loc[date]
        current_upper = vix_upper.loc[date]

        if pd.isna(current_ma) or pd.isna(current_upper):
            continue

        if in_position:
            days_held += 1
            # Exit conditions:
            # 1. VIX drops back below its 20-day MA
            # 2. Held for 5+ trading days
            # 3. Stop loss: SPY dropped 3% from entry
            pct_change = (current_spy - entry_price) / entry_price

            if current_vix < current_ma or days_held >= 5 or pct_change <= -0.03:
                portfolio.sell("SPY", all_shares=True, date=date_str)
                in_position = False
                entry_date = None
                entry_price = None
                days_held = 0
        else:
            # Entry: VIX above upper Bollinger Band
            if current_vix > current_upper:
                result = portfolio.buy("SPY", dollars=portfolio.cash * 0.5, date=date_str)
                if result:
                    in_position = True
                    entry_date = date_str
                    entry_price = current_spy
                    days_held = 0

    # Close any remaining position
    if in_position and dates:
        last_date = dates[-1].strftime("%Y-%m-%d") if hasattr(dates[-1], "strftime") else str(dates[-1])[:10]
        portfolio.sell("SPY", all_shares=True, date=last_date)
