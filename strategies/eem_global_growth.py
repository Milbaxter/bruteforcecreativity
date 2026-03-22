"""
EEM Global Growth Direction

Hypothesis: EEM (iShares MSCI Emerging Markets ETF) direction captures global
growth dynamics. When emerging markets are trending up, global demand is strong,
which benefits commodity producers and growth tech. When EEM is trending down,
global demand is weakening, favoring domestic safety plays.

Combined with Wikipedia "Economy_of_China" attention: China is the largest
EM economy. Rising wiki attention during EEM uptrend confirms the global
growth narrative. Rising attention during EEM downtrend signals worry.

Signals:
1. WHY: EEM price trend (7d/15d MA crossover system)
2. WHEN: EEM rising → GDX (commodity demand) or SOXX (global tech)
3. WHEN: EEM falling → GLD (safety) or XLF (domestic financial)
4. CONFIRMATION: Wiki China attention direction picks within pair

Eccentricity: Emerging market ETF as global growth thermometer + Wikipedia
geopolitical attention. Cross-border macro signal with behavioral confirmation.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "EEM Global Growth",
    "hypothesis": "EEM direction captures global growth dynamics; combined with Wikipedia China attention for sector allocation.",
    "universe": ["GDX", "SOXX", "GLD", "XLF", "EEM"],
    "entry": "EEM up + China wiki up: GDX. EEM up: SOXX. EEM down + China wiki up: GLD. EEM down: XLF.",
    "exit": "Hold 5 days, reassess; -4% stop loss",
    "position_size": "70% of capital per trade",
    "eccentricity": "Emerging market trend as global growth proxy + Wikipedia geopolitical attention.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    eem = data_fetcher.get_prices("EEM", start=start_date, end=end_date)
    if isinstance(eem.columns, pd.MultiIndex):
        eem.columns = eem.columns.get_level_values(0)
    eem_close = eem["Close"].dropna()

    gdx = data_fetcher.get_prices("GDX", start=start_date, end=end_date)
    if isinstance(gdx.columns, pd.MultiIndex):
        gdx.columns = gdx.columns.get_level_values(0)
    gdx_close = gdx["Close"].dropna()

    soxx = data_fetcher.get_prices("SOXX", start=start_date, end=end_date)
    if isinstance(soxx.columns, pd.MultiIndex):
        soxx.columns = soxx.columns.get_level_values(0)
    soxx_close = soxx["Close"].dropna()

    gld = data_fetcher.get_prices("GLD", start=start_date, end=end_date)
    if isinstance(gld.columns, pd.MultiIndex):
        gld.columns = gld.columns.get_level_values(0)
    gld_close = gld["Close"].dropna()

    xlf = data_fetcher.get_prices("XLF", start=start_date, end=end_date)
    if isinstance(xlf.columns, pd.MultiIndex):
        xlf.columns = xlf.columns.get_level_values(0)
    xlf_close = xlf["Close"].dropna()

    vix = data_fetcher.get_vix(start=start_date, end=end_date)

    wiki_china = data_fetcher.get_wikipedia_pageviews("Economy_of_China", start=start_date, end=end_date)

    if eem_close.empty or gdx_close.empty:
        return

    eem_ma7 = eem_close.rolling(7).mean()
    eem_ma15 = eem_close.rolling(15).mean()

    wiki_ma7 = wiki_china.rolling(7).mean() if not wiki_china.empty else pd.Series(dtype=float)
    wiki_ma21 = wiki_china.rolling(21).mean() if not wiki_china.empty else pd.Series(dtype=float)

    close_map = {"GDX": gdx_close, "SOXX": soxx_close, "GLD": gld_close, "XLF": xlf_close}
    trading_days = gdx_close.index.strftime("%Y-%m-%d").tolist()

    in_trade = False
    trade_ticker = None
    entry_date = None
    entry_price = None

    for i, date_str in enumerate(trading_days):
        date_ts = pd.Timestamp(date_str)

        # Exit
        if in_trade:
            days_held = (date_ts - pd.Timestamp(entry_date)).days
            close_s = close_map.get(trade_ticker, gdx_close)
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

        # Signal
        if not in_trade and i >= 20:
            eem_mask = eem_close.index <= date_ts
            m7 = eem_ma7.dropna().index <= date_ts
            m15 = eem_ma15.dropna().index <= date_ts
            if not eem_mask.any() or not m7.any() or not m15.any():
                continue

            eem_p = eem_close[eem_mask].iloc[-1]
            eem_7 = eem_ma7.dropna()[m7].iloc[-1]
            eem_15 = eem_ma15.dropna()[m15].iloc[-1]
            eem_rising = eem_p > eem_7 and eem_7 > eem_15

            # VIX
            vix_mask = vix.index <= date_ts
            if vix_mask.any() and vix[vix_mask].iloc[-1] > 40:
                continue

            # Wiki China trend
            wiki_rising = False
            if not wiki_ma7.empty and not wiki_ma21.empty:
                w7 = wiki_ma7.dropna().index <= date_ts
                w21 = wiki_ma21.dropna().index <= date_ts
                if w7.any() and w21.any():
                    wiki_rising = wiki_ma7.dropna()[w7].iloc[-1] > wiki_ma21.dropna()[w21].iloc[-1]

            # Asset selection
            if eem_rising:
                ticker = "GDX" if wiki_rising else "SOXX"
            else:
                ticker = "GLD" if wiki_rising else "XLF"

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
