"""
Wikipedia Elon Musk Contrarian TSLA

Hypothesis: Elon Musk Wikipedia pageview spikes coincide with controversy/drama.
After the drama peaks (pageviews start declining from a spike), TSLA tends to bounce
because the negative narrative fades. When Musk wiki views spike AND TSLA has pulled
back, the peak-attention moment is a contrarian buy.

Also: when crypto fear/greed is in fear territory, growth names like TSLA sell off
extra hard, making this a double-contrarian signal.

Signals:
1. WHY: Wikipedia "Elon_Musk" pageviews were elevated recently (>1.3x 20d avg)
   but have started declining (current < 3-day ago) = attention fading
2. WHEN: TSLA is 5%+ below its 10-day high (pullback entry)
3. WHEN NOT: TSLA is in persistent downtrend (below 30-day MA by >10%)

Eccentricity: Wikipedia drama tracking as a stock signal. Way too embarrassing
for any institution.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Wiki Elon Contrarian TSLA",
    "hypothesis": "Elon Musk Wikipedia attention peaks mark TSLA controversy bottoms; fading attention + TSLA pullback = contrarian entry.",
    "universe": ["TSLA"],
    "entry": "Buy TSLA when Elon wiki attention fading from spike + TSLA pullback 5%+ from 10d high",
    "exit": "Sell after 5 trading days or +6% gain or -4% stop loss",
    "position_size": "50% of capital per trade",
    "eccentricity": "Wikipedia celebrity drama as stock signal. Would never survive institutional due diligence.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    tsla = data_fetcher.get_prices("TSLA", start=start_date, end=end_date)
    if isinstance(tsla.columns, pd.MultiIndex):
        tsla.columns = tsla.columns.get_level_values(0)
    tsla_close = tsla["Close"].dropna()

    # Wikipedia pageviews for Elon Musk
    wiki_elon = data_fetcher.get_wikipedia_pageviews("Elon_Musk", start=start_date, end=end_date)

    # Crypto fear/greed as secondary risk signal
    crypto_fg = data_fetcher.get_crypto_fear_greed(days=500)

    if tsla_close.empty or wiki_elon.empty:
        return

    # Rolling averages
    wiki_ma20 = wiki_elon.rolling(20).mean()
    tsla_ma30 = tsla_close.rolling(30).mean()
    tsla_high10 = tsla_close.rolling(10).max()

    trading_days = tsla_close.index.strftime("%Y-%m-%d").tolist()
    in_trade = False
    entry_date = None
    entry_price = None

    for i, date_str in enumerate(trading_days):
        date_ts = pd.Timestamp(date_str)
        price = tsla_close.iloc[i]

        # Exit
        if in_trade:
            days_held = (date_ts - pd.Timestamp(entry_date)).days
            pct_change = (price - entry_price) / entry_price * 100
            if days_held >= 5 or pct_change >= 6.0 or pct_change <= -4.0:
                portfolio.sell("TSLA", all_shares=True, date=date_str)
                in_trade = False
                entry_date = None
                entry_price = None
                continue

        # Entry
        if not in_trade and i >= 25:
            # Wiki attention: recently elevated (any of last 5 days > 1.3x 20d avg)
            recent_elevated = False
            current_declining = False

            wiki_mask = wiki_elon.index <= date_ts
            if not wiki_mask.any():
                continue
            recent_wiki = wiki_elon[wiki_mask].tail(7)
            if len(recent_wiki) < 5:
                continue

            ma20_mask = wiki_ma20.dropna().index <= date_ts
            if not ma20_mask.any():
                continue
            current_ma20 = wiki_ma20.dropna()[ma20_mask].iloc[-1]

            # Check if any of last 5 days had elevated attention
            if current_ma20 > 0:
                for val in recent_wiki.iloc[-5:]:
                    if val > current_ma20 * 1.3:
                        recent_elevated = True
                        break

            # Check if attention is declining (current < 3 days ago)
            if len(recent_wiki) >= 4:
                if recent_wiki.iloc[-1] < recent_wiki.iloc[-4]:
                    current_declining = True

            if not recent_elevated or not current_declining:
                continue

            # TSLA pullback: 5%+ below 10-day high
            high10_mask = tsla_high10.dropna().index <= date_ts
            if not high10_mask.any():
                continue
            recent_high = tsla_high10.dropna()[high10_mask].iloc[-1]
            pullback_pct = (recent_high - price) / recent_high * 100
            if pullback_pct < 5.0:
                continue

            # Not in persistent crash (not below 30d MA by > 10%)
            ma30_mask = tsla_ma30.dropna().index <= date_ts
            if not ma30_mask.any():
                continue
            current_ma30 = tsla_ma30.dropna()[ma30_mask].iloc[-1]
            if current_ma30 > 0 and (current_ma30 - price) / current_ma30 * 100 > 10.0:
                continue

            dollars = portfolio.cash * 0.5
            if dollars > 100:
                result = portfolio.buy("TSLA", dollars=dollars, date=date_str)
                if result:
                    in_trade = True
                    entry_date = date_str
                    entry_price = price

    if in_trade:
        portfolio.sell("TSLA", all_shares=True, date=trading_days[-1])
