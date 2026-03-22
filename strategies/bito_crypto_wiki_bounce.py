"""
BITO Crypto Fear Wiki Bounce

Hypothesis: When Bitcoin Wikipedia pageviews spike (retail attention) AND crypto
fear/greed is in fear territory (< 35), it signals peak panic among retail crypto
investors. BITO (ProShares Bitcoin Strategy ETF, ~$15-25/share) lets us trade
this signal with small capital. The wiki spike during fear = contrarian entry.

Uses BITO instead of BTC-USD because BTC is too expensive per share for $10K capital.

Signals:
1. WHY: Bitcoin Wikipedia pageviews spike > 1.3x 14-day rolling average
2. WHEN: Crypto Fear & Greed index < 35 (fear) + BITO below 5-day MA
3. WHEN NOT: BITO already bounced > 5% from 3-day low

Eccentricity: Wikipedia crypto attention as panic proxy, traded via cheap ETF.
Institutions don't monitor Wikipedia for trade signals.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "BITO Crypto Wiki Bounce",
    "hypothesis": "Bitcoin Wikipedia attention spikes during crypto fear mark retail panic bottoms; BITO catches the bounce cheaply.",
    "universe": ["BITO"],
    "entry": "Buy BITO when BTC wiki views spike + crypto fear < 35 + BITO below 5d MA",
    "exit": "Sell after 4 trading days or +5% gain or -4% stop loss",
    "position_size": "50% of capital per trade",
    "eccentricity": "Wikipedia pageview monitoring for crypto ETF trading. No institutional quant tracks Wikipedia.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    bito = data_fetcher.get_prices("BITO", start=start_date, end=end_date)
    if isinstance(bito.columns, pd.MultiIndex):
        bito.columns = bito.columns.get_level_values(0)
    bito_close = bito["Close"].dropna()

    wiki_btc = data_fetcher.get_wikipedia_pageviews("Bitcoin", start=start_date, end=end_date)
    crypto_fg = data_fetcher.get_crypto_fear_greed(days=500)

    if bito_close.empty or wiki_btc.empty or crypto_fg.empty:
        return

    wiki_ma14 = wiki_btc.rolling(14).mean()
    bito_ma5 = bito_close.rolling(5).mean()

    trading_days = bito_close.index.strftime("%Y-%m-%d").tolist()
    in_trade = False
    entry_date = None
    entry_price = None

    for i, date_str in enumerate(trading_days):
        date_ts = pd.Timestamp(date_str)
        price = bito_close.iloc[i]

        # Exit
        if in_trade:
            days_held = (date_ts - pd.Timestamp(entry_date)).days
            pct_change = (price - entry_price) / entry_price * 100
            if days_held >= 4 or pct_change >= 5.0 or pct_change <= -4.0:
                portfolio.sell("BITO", all_shares=True, date=date_str)
                in_trade = False
                entry_date = None
                entry_price = None
                continue

        # Entry
        if not in_trade and i >= 20:
            # Signal 1: Bitcoin wiki views > 1.3x 14-day average
            wiki_mask = wiki_btc.index <= date_ts
            if not wiki_mask.any():
                continue
            current_wiki = wiki_btc[wiki_mask].iloc[-1]

            ma_mask = wiki_ma14.dropna().index <= date_ts
            if not ma_mask.any():
                continue
            current_ma = wiki_ma14.dropna()[ma_mask].iloc[-1]
            if current_ma <= 0 or current_wiki < current_ma * 1.3:
                continue

            # Signal 2: Crypto Fear & Greed < 35
            fg_mask = crypto_fg.index <= date_ts
            if not fg_mask.any():
                continue
            current_fg = crypto_fg[fg_mask].iloc[-1]
            if current_fg >= 35:
                continue

            # Signal 3: BITO below 5-day MA
            ma5_mask = bito_ma5.dropna().index <= date_ts
            if not ma5_mask.any():
                continue
            if price >= bito_ma5.dropna()[ma5_mask].iloc[-1]:
                continue

            # Filter: not already bounced > 5% from 3-day low
            if i >= 3:
                recent_low = bito_close.iloc[max(0, i-3):i+1].min()
                bounce = (price - recent_low) / recent_low * 100
                if bounce > 5.0:
                    continue

            dollars = portfolio.cash * 0.5
            if dollars > 50:
                result = portfolio.buy("BITO", dollars=dollars, date=date_str)
                if result:
                    in_trade = True
                    entry_date = date_str
                    entry_price = price

    if in_trade:
        portfolio.sell("BITO", all_shares=True, date=trading_days[-1])
