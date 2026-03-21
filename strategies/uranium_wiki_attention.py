"""
Uranium Wiki Attention — buy uranium stocks when nuclear attention spikes but prices haven't.

Thesis: Wikipedia pageviews for "Nuclear_power" spike on geopolitical events, policy
announcements, and energy crises. URA (Global X Uranium ETF) often lags the attention
spike by 2-5 days because: (1) uranium is a niche sector most traders don't monitor,
(2) the fundamental connection between attention and stock price takes time to propagate
through news → analyst coverage → fund flows.

Combined signals: Wiki pageview spike > 1.5 std dev + URA flat in past 5 days (hasn't
moved yet) + URA above 50-day MA (not in structural downtrend). This 3-signal combo
ensures we buy only when attention is genuinely elevated but not yet priced in.

Eccentricity: Wikipedia pageviews as a leading indicator for a niche commodity ETF.
No institutional investor monitors Wikipedia traffic for uranium stocks.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Uranium Wiki Attention",
    "hypothesis": "Wikipedia Nuclear_power pageview spikes lead URA price moves by 2-5 days. Attention rises before the market prices in the narrative shift.",
    "universe": ["URA", "SPY"],
    "entry": "Buy URA when Nuclear_power wiki views > 1.5 std dev above 30d mean AND URA 5d return between -2% and +1% AND URA > 50d MA",
    "exit": "Sell after 7 days or +5%/-3% stop",
    "position_size": "80% of capital per trade",
    "eccentricity": "Wikipedia pageviews as leading indicator for niche commodity ETF. No fund watches Wikipedia traffic for uranium trades.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Fetch Wikipedia pageviews for Nuclear power
    wiki = data_fetcher.get_wikipedia_pageviews("Nuclear_power")
    ura = data_fetcher.get_prices("URA", start=start_date, end=end_date)

    if ura.empty:
        return

    ura_close = ura["Close"].dropna()

    if wiki.empty or len(wiki) < 30:
        return

    # Convert wiki index to datetime
    wiki.index = pd.to_datetime(wiki.index)
    ura_close.index = pd.to_datetime(ura_close.index)

    # Compute wiki z-score (rolling 30-day)
    wiki_mean = wiki.rolling(30).mean()
    wiki_std = wiki.rolling(30).std()
    wiki_zscore = (wiki - wiki_mean) / wiki_std

    # Reindex wiki z-score to trading days (forward fill)
    wiki_aligned = wiki_zscore.reindex(ura_close.index, method="ffill")

    # Compute URA signals
    ura_ret_5d = ura_close.pct_change(5)
    ura_ma50 = ura_close.rolling(50).mean()

    in_trade = False
    entry_price = None
    days_held = 0

    start_idx = 55  # need 50d MA + some buffer

    for i in range(start_idx, len(ura_close)):
        date_str = ura_close.index[i].strftime("%Y-%m-%d")
        price = float(ura_close.iloc[i])

        if in_trade:
            days_held += 1
            pnl_pct = (price - entry_price) / entry_price

            if days_held >= 7 or pnl_pct >= 0.05 or pnl_pct <= -0.03:
                portfolio.sell("URA", all_shares=True, date=date_str)
                in_trade = False
                entry_price = None
                days_held = 0

        elif not in_trade:
            wiki_z = float(wiki_aligned.iloc[i]) if pd.notna(wiki_aligned.iloc[i]) else 0
            ret_5d = float(ura_ret_5d.iloc[i]) if pd.notna(ura_ret_5d.iloc[i]) else 0
            ma50 = float(ura_ma50.iloc[i]) if pd.notna(ura_ma50.iloc[i]) else 0

            # Entry: wiki attention spike + URA hasn't moved + above trend
            if wiki_z > 1.5 and -0.02 <= ret_5d <= 0.01 and price > ma50:
                result = portfolio.buy("URA", dollars=portfolio.cash * 0.8, date=date_str)
                if result:
                    in_trade = True
                    entry_price = price
                    days_held = 0

    # Close remaining position
    if in_trade:
        last_date = ura_close.index[-1].strftime("%Y-%m-%d")
        portfolio.sell("URA", all_shares=True, date=last_date)
