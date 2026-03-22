"""
ITB Housing Cycle Direction

Hypothesis: ITB (iShares U.S. Home Construction ETF) captures the housing cycle
which is tightly linked to interest rates and consumer confidence:

- ITB rising: housing market healthy, rates favorable, consumer confident → risk-on
- ITB falling: housing stress, rates too high or credit tightening → risk-off

Housing leads the economy by 6-12 months — homebuilder stocks price in
future economic conditions before other sectors react.

Combined with Wikipedia "Housing_bubble" attention: rising bubble attention
during ITB decline = genuine housing concern.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "ITB Housing Cycle",
    "hypothesis": "ITB homebuilder direction captures housing/rate cycle for sector allocation.",
    "universe": ["SOXX", "XLF", "GDX", "GLD", "ITB"],
    "entry": "ITB up: SOXX/XLF. ITB down: GDX/GLD. Wiki housing bubble attention picks within pair.",
    "exit": "Hold 5 days, reassess; -4% stop loss",
    "position_size": "70% of capital per trade",
    "eccentricity": "Homebuilder ETF as economic leading indicator + Wikipedia housing bubble attention.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    itb = data_fetcher.get_prices("ITB", start=start_date, end=end_date)
    if isinstance(itb.columns, pd.MultiIndex):
        itb.columns = itb.columns.get_level_values(0)
    itb_close = itb["Close"].dropna()

    soxx = data_fetcher.get_prices("SOXX", start=start_date, end=end_date)
    if isinstance(soxx.columns, pd.MultiIndex):
        soxx.columns = soxx.columns.get_level_values(0)
    soxx_close = soxx["Close"].dropna()

    xlf = data_fetcher.get_prices("XLF", start=start_date, end=end_date)
    if isinstance(xlf.columns, pd.MultiIndex):
        xlf.columns = xlf.columns.get_level_values(0)
    xlf_close = xlf["Close"].dropna()

    gdx = data_fetcher.get_prices("GDX", start=start_date, end=end_date)
    if isinstance(gdx.columns, pd.MultiIndex):
        gdx.columns = gdx.columns.get_level_values(0)
    gdx_close = gdx["Close"].dropna()

    gld = data_fetcher.get_prices("GLD", start=start_date, end=end_date)
    if isinstance(gld.columns, pd.MultiIndex):
        gld.columns = gld.columns.get_level_values(0)
    gld_close = gld["Close"].dropna()

    vix = data_fetcher.get_vix(start=start_date, end=end_date)
    wiki = data_fetcher.get_wikipedia_pageviews("United_States_housing_bubble", start=start_date, end=end_date)

    if itb_close.empty or soxx_close.empty:
        return

    itb_ma7 = itb_close.rolling(7).mean()
    itb_ma15 = itb_close.rolling(15).mean()
    wiki_ma7 = wiki.rolling(7).mean() if not wiki.empty else pd.Series(dtype=float)
    wiki_ma21 = wiki.rolling(21).mean() if not wiki.empty else pd.Series(dtype=float)

    close_map = {"SOXX": soxx_close, "XLF": xlf_close, "GDX": gdx_close, "GLD": gld_close}
    trading_days = soxx_close.index.strftime("%Y-%m-%d").tolist()

    in_trade = False
    trade_ticker = None
    entry_date = None
    entry_price = None

    for i, date_str in enumerate(trading_days):
        date_ts = pd.Timestamp(date_str)

        if in_trade:
            days_held = (date_ts - pd.Timestamp(entry_date)).days
            close_s = close_map.get(trade_ticker, soxx_close)
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

        if not in_trade and i >= 20:
            itb_mask = itb_close.index <= date_ts
            m7 = itb_ma7.dropna().index <= date_ts
            m15 = itb_ma15.dropna().index <= date_ts
            if not itb_mask.any() or not m7.any() or not m15.any():
                continue

            itb_p = itb_close[itb_mask].iloc[-1]
            itb_7 = itb_ma7.dropna()[m7].iloc[-1]
            itb_15 = itb_ma15.dropna()[m15].iloc[-1]
            itb_rising = itb_p > itb_7 and itb_7 > itb_15

            vix_mask = vix.index <= date_ts
            if vix_mask.any() and vix[vix_mask].iloc[-1] > 40:
                continue

            wiki_rising = False
            if not wiki_ma7.empty and not wiki_ma21.empty:
                w7 = wiki_ma7.dropna().index <= date_ts
                w21 = wiki_ma21.dropna().index <= date_ts
                if w7.any() and w21.any():
                    wiki_rising = wiki_ma7.dropna()[w7].iloc[-1] > wiki_ma21.dropna()[w21].iloc[-1]

            if itb_rising:
                ticker = "SOXX" if not wiki_rising else "XLF"
            else:
                ticker = "GDX" if wiki_rising else "GLD"

            close_s = close_map[ticker]
            p_mask = close_s.index <= date_ts
            if not p_mask.any():
                continue
            price = close_s[p_mask].iloc[-1]

            dollars = portfolio.cash * 0.7
            if dollars > 100:
                result = portfolio.buy(ticker, dollars=dollars, date=date_str)
                if result:
                    in_trade = True
                    trade_ticker = ticker
                    entry_date = date_str
                    entry_price = price

    if in_trade and trade_ticker:
        portfolio.sell(trade_ticker, all_shares=True, date=trading_days[-1])
