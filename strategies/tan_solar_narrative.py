"""
TAN Solar Energy Narrative

Hypothesis: TAN (Invesco Solar ETF) captures the green energy/climate policy
narrative. When TAN trends up, it signals policy support for clean energy and
risk-on sentiment for growth. When TAN trends down, it signals policy headwinds
or value rotation.

Combined with Wikipedia "Climate_change" attention: rising climate attention
during TAN uptrend confirms the green narrative has momentum.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "TAN Solar Narrative",
    "hypothesis": "TAN solar ETF direction captures green energy/policy narrative for sector allocation.",
    "universe": ["SOXX", "XLF", "GDX", "GLD", "TAN"],
    "entry": "TAN up + wiki climate up: SOXX. TAN up: XLF. TAN down + wiki up: GDX. TAN down: GLD.",
    "exit": "Hold 5 days, reassess; -4% stop loss",
    "position_size": "70% of capital per trade",
    "eccentricity": "Solar ETF as policy/growth narrative signal + Wikipedia climate attention.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    tan = data_fetcher.get_prices("TAN", start=start_date, end=end_date)
    if isinstance(tan.columns, pd.MultiIndex):
        tan.columns = tan.columns.get_level_values(0)
    tan_close = tan["Close"].dropna()

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
    wiki = data_fetcher.get_wikipedia_pageviews("Climate_change", start=start_date, end=end_date)

    if tan_close.empty or soxx_close.empty:
        return

    tan_ma7 = tan_close.rolling(7).mean()
    tan_ma15 = tan_close.rolling(15).mean()
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
            tan_mask = tan_close.index <= date_ts
            m7 = tan_ma7.dropna().index <= date_ts
            m15 = tan_ma15.dropna().index <= date_ts
            if not tan_mask.any() or not m7.any() or not m15.any():
                continue

            tan_p = tan_close[tan_mask].iloc[-1]
            tan_7 = tan_ma7.dropna()[m7].iloc[-1]
            tan_15 = tan_ma15.dropna()[m15].iloc[-1]
            tan_rising = tan_p > tan_7 and tan_7 > tan_15

            vix_mask = vix.index <= date_ts
            if vix_mask.any() and vix[vix_mask].iloc[-1] > 40:
                continue

            wiki_rising = False
            if not wiki_ma7.empty and not wiki_ma21.empty:
                w7 = wiki_ma7.dropna().index <= date_ts
                w21 = wiki_ma21.dropna().index <= date_ts
                if w7.any() and w21.any():
                    wiki_rising = wiki_ma7.dropna()[w7].iloc[-1] > wiki_ma21.dropna()[w21].iloc[-1]

            if tan_rising:
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
