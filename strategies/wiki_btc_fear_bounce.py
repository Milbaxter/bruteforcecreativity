"""
Wikipedia Bitcoin Fear Bounce

Hypothesis: Spikes in Bitcoin's Wikipedia pageviews during crypto fear conditions
signal peak retail panic attention. When the crowd is panic-searching Bitcoin on
Wikipedia while the price has pulled back, it often marks the bottom before a bounce.

Signals:
1. WHY: Wikipedia Bitcoin pageviews spike > 1.5x their 20-day rolling average
2. WHEN: Crypto Fear & Greed index < 35 (fear territory) + BTC below 10-day MA
3. WHEN NOT: BTC already bounced >3% from recent low (too late)

Eccentricity: Combines Wikipedia attention data (too weird for institutional models)
with crypto sentiment index (too alt-data for risk committees) for a specific
behavioral thesis: retail panic-searches Wikipedia during dips, creating a
measurable contrarian signal.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Wikipedia BTC Fear Bounce",
    "hypothesis": "Wikipedia Bitcoin pageview spikes during crypto fear indicate peak retail panic, which often marks short-term bottoms before a bounce.",
    "universe": ["BTC-USD"],
    "entry": "Buy BTC when Wikipedia Bitcoin pageviews > 1.5x 20-day avg AND crypto fear/greed < 35 AND BTC below 10-day MA",
    "exit": "Sell after 3 trading days or +5% gain or -4% stop loss",
    "position_size": "50% of capital per trade",
    "eccentricity": "Wikipedia attention as panic proxy + crypto fear/greed double-confirmation. No fund would cite Wikipedia pageviews in an IC memo.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Fetch data
    btc = data_fetcher.get_prices("BTC-USD", start=start_date, end=end_date)
    if isinstance(btc.columns, pd.MultiIndex):
        btc.columns = btc.columns.get_level_values(0)
    btc_close = btc["Close"].dropna()

    # Wikipedia pageviews for Bitcoin
    wiki = data_fetcher.get_wikipedia_pageviews("Bitcoin", start=start_date, end=end_date)

    # Crypto Fear & Greed index
    crypto_fg = data_fetcher.get_crypto_fear_greed(days=500)

    if btc_close.empty or wiki.empty or crypto_fg.empty:
        return

    # Compute rolling 20-day average of Wikipedia pageviews
    wiki_ma20 = wiki.rolling(20).mean()

    # Compute 10-day MA of BTC
    btc_ma10 = btc_close.rolling(10).mean()

    # Iterate through trading days
    trading_days = btc_close.index.strftime("%Y-%m-%d").tolist()
    in_trade = False
    entry_date = None
    entry_price = None

    for i, date_str in enumerate(trading_days):
        date_ts = pd.Timestamp(date_str)
        price = btc_close.iloc[i]

        # Check exit conditions first
        if in_trade:
            days_held = (date_ts - pd.Timestamp(entry_date)).days
            pct_change = (price - entry_price) / entry_price * 100

            # Exit: 3+ trading days OR +5% gain OR -4% stop
            if days_held >= 3 or pct_change >= 5.0 or pct_change <= -4.0:
                portfolio.sell("BTC-USD", all_shares=True, date=date_str)
                in_trade = False
                entry_date = None
                entry_price = None
                continue

        # Check entry conditions
        if not in_trade and i >= 25:  # Need enough history for rolling calcs
            # Get Wikipedia pageviews for this date
            wiki_dates = wiki.index
            wiki_mask = wiki_dates <= date_ts
            if not wiki_mask.any():
                continue
            current_wiki = wiki[wiki_mask].iloc[-1]

            wiki_ma_dates = wiki_ma20.dropna().index
            wiki_ma_mask = wiki_ma_dates <= date_ts
            if not wiki_ma_mask.any():
                continue
            current_wiki_ma = wiki_ma20.dropna()[wiki_ma_mask].iloc[-1]

            # Signal 1: Wikipedia pageviews spike > 1.5x 20-day average
            if current_wiki_ma > 0 and current_wiki < current_wiki_ma * 1.5:
                continue

            # Signal 2: Crypto Fear & Greed < 35
            fg_mask = crypto_fg.index <= date_ts
            if not fg_mask.any():
                continue
            current_fg = crypto_fg[fg_mask].iloc[-1]
            if current_fg >= 35:
                continue

            # Signal 3: BTC below 10-day MA
            ma10_mask = btc_ma10.dropna().index <= date_ts
            if not ma10_mask.any():
                continue
            current_ma10 = btc_ma10.dropna()[ma10_mask].iloc[-1]
            if price >= current_ma10:
                continue

            # Signal 4: BTC hasn't already bounced >3% from 5-day low
            if i >= 5:
                recent_low = btc_close.iloc[max(0, i-5):i+1].min()
                bounce_pct = (price - recent_low) / recent_low * 100
                if bounce_pct > 3.0:
                    continue

            # All signals aligned — buy
            dollars = portfolio.cash * 0.5
            if dollars > 100:
                result = portfolio.buy("BTC-USD", dollars=dollars, date=date_str)
                if result:
                    in_trade = True
                    entry_date = date_str
                    entry_price = price

    # Close any remaining position
    if in_trade:
        last_date = trading_days[-1]
        portfolio.sell("BTC-USD", all_shares=True, date=last_date)
