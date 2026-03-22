"""
Copper Economic Signal ("Dr. Copper")

Hypothesis: Copper is called "Dr. Copper" because it's used in virtually every
industry — construction, electronics, transport. COPX (Global X Copper Miners ETF)
direction is one of the most reliable economic health indicators:

- COPX rising: industrial demand strong → economy expanding → risk-on
- COPX falling: industrial demand weakening → economy slowing → risk-off

Combined with Wikipedia "Copper" attention: rising attention during COPX uptrend
confirms the industrial narrative. Rising attention during downtrend = supply concern.

Signals:
1. WHY: COPX 7d/15d MA trend system
2. WHEN: COPX rising → SOXX/XLF (industrial growth); COPX falling → GDX/GLD (safety)
3. CONFIRMATION: Wiki copper attention determines which paired asset
4. WHEN NOT: VIX > 40

Eccentricity: Copper mining ETF as economic bellwether + Wikipedia copper attention
for supply/demand narrative. Classical economic indicator with behavioral overlay.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Dr Copper Economic Signal",
    "hypothesis": "COPX copper miners direction captures industrial demand and economic health for sector allocation.",
    "universe": ["SOXX", "XLF", "GDX", "GLD", "COPX"],
    "entry": "COPX up + wiki copper up: SOXX. COPX up: XLF. COPX down + wiki up: GDX. COPX down: GLD.",
    "exit": "Hold 5 days, reassess; -4% stop loss",
    "position_size": "70% of capital per trade",
    "eccentricity": "Dr. Copper economic signal + Wikipedia attention. Industrial metal as investment compass.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    copx = data_fetcher.get_prices("COPX", start=start_date, end=end_date)
    if isinstance(copx.columns, pd.MultiIndex):
        copx.columns = copx.columns.get_level_values(0)
    copx_close = copx["Close"].dropna()

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

    wiki_copper = data_fetcher.get_wikipedia_pageviews("Copper", start=start_date, end=end_date)

    if copx_close.empty or soxx_close.empty:
        return

    copx_ma7 = copx_close.rolling(7).mean()
    copx_ma15 = copx_close.rolling(15).mean()

    wiki_ma7 = wiki_copper.rolling(7).mean() if not wiki_copper.empty else pd.Series(dtype=float)
    wiki_ma21 = wiki_copper.rolling(21).mean() if not wiki_copper.empty else pd.Series(dtype=float)

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
            copx_mask = copx_close.index <= date_ts
            m7 = copx_ma7.dropna().index <= date_ts
            m15 = copx_ma15.dropna().index <= date_ts
            if not copx_mask.any() or not m7.any() or not m15.any():
                continue

            copx_p = copx_close[copx_mask].iloc[-1]
            copx_7 = copx_ma7.dropna()[m7].iloc[-1]
            copx_15 = copx_ma15.dropna()[m15].iloc[-1]
            copx_rising = copx_p > copx_7 and copx_7 > copx_15

            vix_mask = vix.index <= date_ts
            if vix_mask.any() and vix[vix_mask].iloc[-1] > 40:
                continue

            wiki_rising = False
            if not wiki_ma7.empty and not wiki_ma21.empty:
                w7 = wiki_ma7.dropna().index <= date_ts
                w21 = wiki_ma21.dropna().index <= date_ts
                if w7.any() and w21.any():
                    wiki_rising = wiki_ma7.dropna()[w7].iloc[-1] > wiki_ma21.dropna()[w21].iloc[-1]

            if copx_rising:
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
