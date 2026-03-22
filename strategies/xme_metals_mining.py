"""
XME Metals Mining Direction

Hypothesis: XME (SPDR S&P Metals & Mining ETF) captures industrial metal demand
which is a direct proxy for manufacturing and construction activity:

- XME rising: industrial activity expanding → global growth → risk-on allocation
- XME falling: industrial slowdown → commodities weakening → safety allocation

XME includes steel, copper, aluminum, and other base metals miners.

Combined with Wikipedia "Mining" attention for narrative confirmation.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "XME Metals Mining Direction",
    "hypothesis": "XME metals/mining ETF direction captures industrial activity for sector allocation.",
    "universe": ["SOXX", "XLF", "GDX", "GLD", "XME"],
    "entry": "XME up: SOXX/XLF. XME down: GDX/GLD. Wiki mining attention picks within pair.",
    "exit": "Hold 5 days, reassess; -4% stop loss",
    "position_size": "70% of capital per trade",
    "eccentricity": "Metals & mining ETF as industrial activity barometer + Wikipedia mining attention.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    xme = data_fetcher.get_prices("XME", start=start_date, end=end_date)
    if isinstance(xme.columns, pd.MultiIndex):
        xme.columns = xme.columns.get_level_values(0)
    xme_close = xme["Close"].dropna()

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
    wiki = data_fetcher.get_wikipedia_pageviews("Mining", start=start_date, end=end_date)

    if xme_close.empty or soxx_close.empty:
        return

    xme_ma7 = xme_close.rolling(7).mean()
    xme_ma15 = xme_close.rolling(15).mean()
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
            xme_mask = xme_close.index <= date_ts
            m7 = xme_ma7.dropna().index <= date_ts
            m15 = xme_ma15.dropna().index <= date_ts
            if not xme_mask.any() or not m7.any() or not m15.any():
                continue

            xme_p = xme_close[xme_mask].iloc[-1]
            xme_7 = xme_ma7.dropna()[m7].iloc[-1]
            xme_15 = xme_ma15.dropna()[m15].iloc[-1]
            xme_rising = xme_p > xme_7 and xme_7 > xme_15

            vix_mask = vix.index <= date_ts
            if vix_mask.any() and vix[vix_mask].iloc[-1] > 40:
                continue

            wiki_rising = False
            if not wiki_ma7.empty and not wiki_ma21.empty:
                w7 = wiki_ma7.dropna().index <= date_ts
                w21 = wiki_ma21.dropna().index <= date_ts
                if w7.any() and w21.any():
                    wiki_rising = wiki_ma7.dropna()[w7].iloc[-1] > wiki_ma21.dropna()[w21].iloc[-1]

            if xme_rising:
                ticker = "SOXX" if wiki_rising else "XLF"
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
