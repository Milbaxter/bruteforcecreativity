"""
JETS Airlines Demand Signal

Hypothesis: JETS (U.S. Global Jets ETF) captures consumer travel demand, which
is a strong proxy for consumer confidence and economic activity. Airlines are
among the first to benefit from economic expansion (travel is discretionary)
and first to suffer in downturns.

- JETS rising: consumer confidence high, travel demand strong → risk-on
- JETS falling: consumer pulling back on travel → risk-off

Combined with Wikipedia "Airline" attention for narrative confirmation:
rising airline wiki during JETS uptrend = travel boom narrative.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "JETS Airline Demand",
    "hypothesis": "JETS airline ETF direction captures consumer confidence/travel demand for sector allocation.",
    "universe": ["SOXX", "XLF", "GDX", "GLD", "JETS"],
    "entry": "JETS up: SOXX/XLF. JETS down: GDX/GLD. Wiki airline attention picks within pair.",
    "exit": "Hold 5 days, reassess; -4% stop loss",
    "position_size": "70% of capital per trade",
    "eccentricity": "Airline ETF as consumer confidence proxy + Wikipedia airline attention.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    jets = data_fetcher.get_prices("JETS", start=start_date, end=end_date)
    if isinstance(jets.columns, pd.MultiIndex):
        jets.columns = jets.columns.get_level_values(0)
    jets_close = jets["Close"].dropna()

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
    wiki = data_fetcher.get_wikipedia_pageviews("Airline", start=start_date, end=end_date)

    if jets_close.empty or soxx_close.empty:
        return

    jets_ma7 = jets_close.rolling(7).mean()
    jets_ma15 = jets_close.rolling(15).mean()
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
            jets_mask = jets_close.index <= date_ts
            m7 = jets_ma7.dropna().index <= date_ts
            m15 = jets_ma15.dropna().index <= date_ts
            if not jets_mask.any() or not m7.any() or not m15.any():
                continue

            jets_p = jets_close[jets_mask].iloc[-1]
            jets_7 = jets_ma7.dropna()[m7].iloc[-1]
            jets_15 = jets_ma15.dropna()[m15].iloc[-1]
            jets_rising = jets_p > jets_7 and jets_7 > jets_15

            vix_mask = vix.index <= date_ts
            if vix_mask.any() and vix[vix_mask].iloc[-1] > 40:
                continue

            wiki_rising = False
            if not wiki_ma7.empty and not wiki_ma21.empty:
                w7 = wiki_ma7.dropna().index <= date_ts
                w21 = wiki_ma21.dropna().index <= date_ts
                if w7.any() and w21.any():
                    wiki_rising = wiki_ma7.dropna()[w7].iloc[-1] > wiki_ma21.dropna()[w21].iloc[-1]

            if jets_rising:
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
