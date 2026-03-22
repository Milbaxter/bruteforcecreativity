"""
Wikipedia Industry Attention Speed

Hypothesis: Wikipedia pageview MOMENTUM for industry-specific articles captures
shifting public/investor attention across sectors. When attention to a particular
industry is accelerating (7d MA rising vs 21d MA), that sector tends to see inflows
as the narrative builds.

Track 4 industry Wikipedia articles and their corresponding sector ETFs:
- "Semiconductor_industry" → SOXX
- "Gold_mining" → GDX
- "Silver" → SLV
- "Banking_in_the_United_States" → XLF

Buy the sector whose Wikipedia article has the highest attention momentum
(7d/21d ratio). Combined with VIX filter for risk management.

Eccentricity: Pure Wikipedia pageview momentum as sector rotation signal.
Using industry-article attention speed to predict sector performance.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Wiki Industry Attention",
    "hypothesis": "Wikipedia industry article attention momentum predicts sector ETF performance. Rising attention = rising demand.",
    "universe": ["SOXX", "GDX", "SLV", "XLF"],
    "entry": "Buy sector whose Wikipedia industry article has highest 7d/21d attention ratio",
    "exit": "Hold 5 days, reassess attention rankings; -4% stop loss",
    "position_size": "70% of capital per trade",
    "eccentricity": "Pure Wikipedia pageview momentum as sector selection. No quant fund uses Wikipedia traffic speed for sector rotation.",
}

WIKI_SECTOR_MAP = [
    ("Semiconductor_industry", "SOXX"),
    ("Gold_mining", "GDX"),
    ("Silver", "SLV"),
    ("Banking_in_the_United_States", "XLF"),
]


def run(data_fetcher, portfolio, start_date, end_date):
    # Fetch sector prices
    sector_prices = {}
    for _, ticker in WIKI_SECTOR_MAP:
        df = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        sector_prices[ticker] = df["Close"].dropna()

    # Fetch Wikipedia data
    wiki_data = {}
    wiki_ma7 = {}
    wiki_ma21 = {}
    for article, ticker in WIKI_SECTOR_MAP:
        try:
            views = data_fetcher.get_wikipedia_pageviews(article, start=start_date, end=end_date)
            if not views.empty:
                wiki_data[ticker] = views
                wiki_ma7[ticker] = views.rolling(7).mean()
                wiki_ma21[ticker] = views.rolling(21).mean()
        except Exception:
            pass

    if len(wiki_data) < 3:
        return

    vix = data_fetcher.get_vix(start=start_date, end=end_date)

    # Use SOXX trading days as reference
    ref_close = sector_prices.get("SOXX", pd.Series(dtype=float))
    if ref_close.empty:
        return

    trading_days = ref_close.index.strftime("%Y-%m-%d").tolist()
    in_trade = False
    trade_ticker = None
    entry_date = None
    entry_price = None

    for i, date_str in enumerate(trading_days):
        date_ts = pd.Timestamp(date_str)

        # Exit
        if in_trade:
            days_held = (date_ts - pd.Timestamp(entry_date)).days
            close_s = sector_prices.get(trade_ticker, ref_close)
            mask = close_s.index <= date_ts
            if mask.any():
                current_price = close_s[mask].iloc[-1]
                pct_change = (current_price - entry_price) / entry_price * 100
                if days_held >= 5 or pct_change <= -4.0 or pct_change >= 5.0:
                    portfolio.sell(trade_ticker, all_shares=True, date=date_str)
                    in_trade = False
                    trade_ticker = None
                    entry_date = None
                    entry_price = None

        # Signal: compute attention momentum for each sector
        if not in_trade and i >= 25:
            # VIX filter
            vix_mask = vix.index <= date_ts
            if vix_mask.any() and vix[vix_mask].iloc[-1] > 40:
                continue

            best_ticker = None
            best_ratio = 0

            for ticker in wiki_data:
                if ticker not in wiki_ma7 or ticker not in wiki_ma21:
                    continue

                ma7_mask = wiki_ma7[ticker].dropna().index <= date_ts
                ma21_mask = wiki_ma21[ticker].dropna().index <= date_ts

                if not ma7_mask.any() or not ma21_mask.any():
                    continue

                short_avg = wiki_ma7[ticker].dropna()[ma7_mask].iloc[-1]
                long_avg = wiki_ma21[ticker].dropna()[ma21_mask].iloc[-1]

                if long_avg > 0:
                    attention_ratio = short_avg / long_avg
                    if attention_ratio > best_ratio:
                        best_ratio = attention_ratio
                        best_ticker = ticker

            if best_ticker is None or best_ratio < 1.0:
                # No sector has rising attention; default to least-attention sector
                # (contrarian: buy what nobody is watching)
                min_ratio = float('inf')
                for ticker in wiki_data:
                    if ticker not in wiki_ma7 or ticker not in wiki_ma21:
                        continue
                    ma7_mask = wiki_ma7[ticker].dropna().index <= date_ts
                    ma21_mask = wiki_ma21[ticker].dropna().index <= date_ts
                    if ma7_mask.any() and ma21_mask.any():
                        short_avg = wiki_ma7[ticker].dropna()[ma7_mask].iloc[-1]
                        long_avg = wiki_ma21[ticker].dropna()[ma21_mask].iloc[-1]
                        if long_avg > 0:
                            ratio = short_avg / long_avg
                            if ratio < min_ratio:
                                min_ratio = ratio
                                best_ticker = ticker

            if best_ticker is None:
                continue

            close_s = sector_prices.get(best_ticker, ref_close)
            p_mask = close_s.index <= date_ts
            if not p_mask.any():
                continue
            price = close_s[p_mask].iloc[-1]

            dollars = portfolio.cash * 0.7
            if dollars > 100:
                result = portfolio.buy(best_ticker, dollars=dollars, date=date_str)
                if result:
                    in_trade = True
                    trade_ticker = best_ticker
                    entry_date = date_str
                    entry_price = price

    if in_trade and trade_ticker:
        portfolio.sell(trade_ticker, all_shares=True, date=trading_days[-1])
