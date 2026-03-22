"""
Wikipedia Financial Panic Breadth

Hypothesis: Track daily Wikipedia pageviews for 5 financial "panic" articles:
Recession, Stock_market_crash, Inflation, Bank_run, Gold. When multiple articles
simultaneously spike above their rolling averages ("panic breadth" is high), it
signals broad public fear, which is a CONTRARIAN buy signal for risk assets.
When panic breadth is low (calm), rotate into more aggressive assets.

Signals:
1. WHY: Count of panic articles > 1.2x their 14-day average
2. WHEN: High breadth (>=3) = buy GLD (safe haven); Low breadth (<=1) = buy SOXX (risk-on);
   Medium breadth (2) = buy XLF (neutral)
3. TIMING: Enter when selected asset is below its 5-day MA (buy the dip within regime)
4. WHEN NOT: VIX > 40

Eccentricity: Wikipedia article breadth as a market sentiment indicator.
Tracking how many fear-related articles spike simultaneously.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Wiki Panic Breadth",
    "hypothesis": "Wikipedia financial panic article breadth (how many spike simultaneously) predicts market risk regime.",
    "universe": ["GLD", "SOXX", "XLF"],
    "entry": "Panic breadth >= 3: buy GLD. Breadth <= 1: buy SOXX. Breadth 2: buy XLF. Enter on dip.",
    "exit": "Sell after 5 trading days or signal reversal or -3% stop loss",
    "position_size": "50% of capital per trade",
    "eccentricity": "Multi-article Wikipedia breadth indicator. No quant model tracks simultaneous panic article spikes.",
}

PANIC_ARTICLES = [
    "Recession",
    "Stock_market_crash",
    "Inflation",
    "Bank_run",
    "Gold",
]


def run(data_fetcher, portfolio, start_date, end_date):
    # Fetch prices
    gld = data_fetcher.get_prices("GLD", start=start_date, end=end_date)
    if isinstance(gld.columns, pd.MultiIndex):
        gld.columns = gld.columns.get_level_values(0)
    gld_close = gld["Close"].dropna()

    soxx = data_fetcher.get_prices("SOXX", start=start_date, end=end_date)
    if isinstance(soxx.columns, pd.MultiIndex):
        soxx.columns = soxx.columns.get_level_values(0)
    soxx_close = soxx["Close"].dropna()

    xlf = data_fetcher.get_prices("XLF", start=start_date, end=end_date)
    if isinstance(xlf.columns, pd.MultiIndex):
        xlf.columns = xlf.columns.get_level_values(0)
    xlf_close = xlf["Close"].dropna()

    vix = data_fetcher.get_vix(start=start_date, end=end_date)

    # Fetch Wikipedia data for all panic articles
    wiki_data = {}
    wiki_ma = {}
    for article in PANIC_ARTICLES:
        try:
            views = data_fetcher.get_wikipedia_pageviews(article, start=start_date, end=end_date)
            if not views.empty:
                wiki_data[article] = views
                wiki_ma[article] = views.rolling(14).mean()
        except Exception:
            pass

    if len(wiki_data) < 3:  # Need at least 3 articles
        return

    # Compute 5-day MAs for entry timing
    gld_ma5 = gld_close.rolling(5).mean()
    soxx_ma5 = soxx_close.rolling(5).mean()
    xlf_ma5 = xlf_close.rolling(5).mean()

    # Use GLD trading days as reference
    trading_days = gld_close.index.strftime("%Y-%m-%d").tolist()
    in_trade = False
    trade_ticker = None
    entry_date = None
    entry_price = None

    for i, date_str in enumerate(trading_days):
        date_ts = pd.Timestamp(date_str)

        # Exit
        if in_trade:
            days_held = (date_ts - pd.Timestamp(entry_date)).days
            if trade_ticker == "GLD":
                close_s = gld_close
            elif trade_ticker == "SOXX":
                close_s = soxx_close
            else:
                close_s = xlf_close

            mask = close_s.index <= date_ts
            if mask.any():
                current_price = close_s[mask].iloc[-1]
                pct_change = (current_price - entry_price) / entry_price * 100
                if days_held >= 5 or pct_change <= -3.0 or pct_change >= 4.0:
                    portfolio.sell(trade_ticker, all_shares=True, date=date_str)
                    in_trade = False
                    trade_ticker = None
                    entry_date = None
                    entry_price = None
                    # Don't continue — can enter new trade same day

        # Entry
        if not in_trade and i >= 20:
            # Compute panic breadth
            breadth = 0
            for article in wiki_data:
                w_mask = wiki_data[article].index <= date_ts
                m_mask = wiki_ma[article].dropna().index <= date_ts
                if w_mask.any() and m_mask.any():
                    current_val = wiki_data[article][w_mask].iloc[-1]
                    current_avg = wiki_ma[article].dropna()[m_mask].iloc[-1]
                    if current_avg > 0 and current_val > current_avg * 1.2:
                        breadth += 1

            # VIX filter
            vix_mask = vix.index <= date_ts
            if vix_mask.any() and vix[vix_mask].iloc[-1] > 40:
                continue

            # Determine target asset based on breadth
            if breadth >= 3:
                ticker = "GLD"
                close_s = gld_close
                ma5 = gld_ma5
            elif breadth <= 1:
                ticker = "SOXX"
                close_s = soxx_close
                ma5 = soxx_ma5
            else:
                ticker = "XLF"
                close_s = xlf_close
                ma5 = xlf_ma5

            # Dip entry: price below 5-day MA
            p_mask = close_s.index <= date_ts
            m5_mask = ma5.dropna().index <= date_ts
            if not p_mask.any() or not m5_mask.any():
                continue

            price = close_s[p_mask].iloc[-1]
            ma5_val = ma5.dropna()[m5_mask].iloc[-1]

            if price >= ma5_val:
                continue

            dollars = portfolio.cash * 0.5
            if dollars > 100:
                result = portfolio.buy(ticker, dollars=dollars, date=date_str)
                if result:
                    in_trade = True
                    trade_ticker = ticker
                    entry_date = date_str
                    entry_price = price

    if in_trade and trade_ticker:
        portfolio.sell(trade_ticker, all_shares=True, date=trading_days[-1])
