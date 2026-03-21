"""
Crypto Weekend Momentum: Buy BTC-USD and ETH-USD on Friday, sell Monday.

Thesis: Crypto trades 24/7 but traditional markets are closed weekends.
Retail traders (who drive crypto more than stocks) are most active on weekends.
FOMO and community engagement peaks when people aren't at work. This creates
weekend pumps, especially during bull markets.

We combine this with a momentum filter: only enter if the 5-day trend is up,
to avoid riding weekends down during corrections.
"""

import pandas as pd

STRATEGY = {
    "name": "Crypto Weekend Momentum",
    "hypothesis": "Crypto rallies on weekends when retail is most active and TradFi can't sell. Combined with a momentum filter, this captures weekend pumps during bullish periods.",
    "universe": ["BTC-USD", "ETH-USD"],
    "entry": "Buy BTC and ETH on Friday close if 5-day momentum is positive",
    "exit": "Sell on Monday close",
    "position_size": "45% BTC, 45% ETH per weekend trade",
    "eccentricity": "Exploits the structural gap between 24/7 crypto markets and M-F TradFi. Institutional crypto desks are often understaffed on weekends.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Fetch crypto prices
    btc = data_fetcher.get_crypto_prices("BTC-USD", start=start_date, end=end_date)
    eth = data_fetcher.get_crypto_prices("ETH-USD", start=start_date, end=end_date)

    if isinstance(btc.columns, pd.MultiIndex):
        btc.columns = btc.columns.get_level_values(0)
    if isinstance(eth.columns, pd.MultiIndex):
        eth.columns = eth.columns.get_level_values(0)

    if btc.empty or eth.empty:
        return

    btc_close = btc["Close"]
    eth_close = eth["Close"]

    # Common trading days
    common = sorted(set(btc_close.index) & set(eth_close.index))
    if len(common) < 10:
        return

    in_position = False

    for i in range(5, len(common)):
        day = common[i]
        day_str = day.strftime("%Y-%m-%d") if hasattr(day, "strftime") else str(day)[:10]
        weekday = day.weekday() if hasattr(day, "weekday") else pd.Timestamp(day).weekday()

        if in_position:
            # Sell on Monday (weekday 0) or Tuesday (weekday 1, if Monday data missing)
            if weekday <= 1:
                portfolio.sell("BTC-USD", all_shares=True, date=day_str)
                portfolio.sell("ETH-USD", all_shares=True, date=day_str)
                in_position = False
        else:
            # Buy on Friday (weekday 4) or Thursday (weekday 3, if Friday data missing)
            if weekday >= 3 and weekday <= 4:
                # Momentum filter: 5-day return positive for BTC
                lookback = common[i - 5]
                if lookback in btc_close.index and day in btc_close.index:
                    btc_5d = (float(btc_close.loc[day]) - float(btc_close.loc[lookback])) / float(btc_close.loc[lookback])

                    if btc_5d > 0:  # Only enter if momentum is up
                        cash = portfolio.cash
                        if cash < 200:
                            continue
                        r1 = portfolio.buy("BTC-USD", dollars=cash * 0.45, date=day_str)
                        r2 = portfolio.buy("ETH-USD", dollars=portfolio.cash * 0.80, date=day_str)
                        if r1 or r2:
                            in_position = True

    # Close remaining
    if in_position and common:
        last = common[-1].strftime("%Y-%m-%d") if hasattr(common[-1], "strftime") else str(common[-1])[:10]
        portfolio.sell("BTC-USD", all_shares=True, date=last)
        portfolio.sell("ETH-USD", all_shares=True, date=last)
