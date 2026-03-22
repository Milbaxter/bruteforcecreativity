"""
DBA Agriculture Direction

Hypothesis: DBA (Invesco DB Agriculture Fund) direction captures agricultural
commodity cycles which track food inflation and global supply/demand. Rising DBA
signals food/commodity inflation → benefits commodity producers (GDX, SLV).
Falling DBA signals stable/deflating food prices → benefits growth (SOXX).

Combined with Wikipedia "Drought" or "Agriculture" attention for weather/supply
narrative confirmation.

Signals:
1. WHY: DBA price trend (7d/15d MA system)
2. WHEN: DBA rising → commodity allocation (GDX/SLV); DBA falling → growth (SOXX/XLF)
3. CONFIRMATION: Wikipedia agriculture attention direction picks within pair
4. WHEN NOT: VIX > 40

Eccentricity: Agriculture commodity trend as a sector allocation signal +
Wikipedia agricultural attention. Food price dynamics as investment signal.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "DBA Agriculture Direction",
    "hypothesis": "DBA agriculture ETF direction captures food inflation cycle; combined with Wikipedia agriculture attention for sector allocation.",
    "universe": ["GDX", "SLV", "SOXX", "XLF", "DBA"],
    "entry": "DBA up + wiki ag up: GDX. DBA up: SLV. DBA down + wiki ag down: SOXX. DBA down: XLF.",
    "exit": "Hold 5 days, reassess; -4% stop loss",
    "position_size": "70% of capital per trade",
    "eccentricity": "Agricultural commodity trend as macro allocation signal + Wikipedia crop attention narrative.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    dba = data_fetcher.get_prices("DBA", start=start_date, end=end_date)
    if isinstance(dba.columns, pd.MultiIndex):
        dba.columns = dba.columns.get_level_values(0)
    dba_close = dba["Close"].dropna()

    gdx = data_fetcher.get_prices("GDX", start=start_date, end=end_date)
    if isinstance(gdx.columns, pd.MultiIndex):
        gdx.columns = gdx.columns.get_level_values(0)
    gdx_close = gdx["Close"].dropna()

    slv = data_fetcher.get_prices("SLV", start=start_date, end=end_date)
    if isinstance(slv.columns, pd.MultiIndex):
        slv.columns = slv.columns.get_level_values(0)
    slv_close = slv["Close"].dropna()

    soxx = data_fetcher.get_prices("SOXX", start=start_date, end=end_date)
    if isinstance(soxx.columns, pd.MultiIndex):
        soxx.columns = soxx.columns.get_level_values(0)
    soxx_close = soxx["Close"].dropna()

    xlf = data_fetcher.get_prices("XLF", start=start_date, end=end_date)
    if isinstance(xlf.columns, pd.MultiIndex):
        xlf.columns = xlf.columns.get_level_values(0)
    xlf_close = xlf["Close"].dropna()

    vix = data_fetcher.get_vix(start=start_date, end=end_date)

    wiki_ag = data_fetcher.get_wikipedia_pageviews("Agriculture", start=start_date, end=end_date)

    if dba_close.empty or gdx_close.empty:
        return

    dba_ma7 = dba_close.rolling(7).mean()
    dba_ma15 = dba_close.rolling(15).mean()

    wiki_ma7 = wiki_ag.rolling(7).mean() if not wiki_ag.empty else pd.Series(dtype=float)
    wiki_ma21 = wiki_ag.rolling(21).mean() if not wiki_ag.empty else pd.Series(dtype=float)

    close_map = {"GDX": gdx_close, "SLV": slv_close, "SOXX": soxx_close, "XLF": xlf_close}
    trading_days = gdx_close.index.strftime("%Y-%m-%d").tolist()

    in_trade = False
    trade_ticker = None
    entry_date = None
    entry_price = None

    for i, date_str in enumerate(trading_days):
        date_ts = pd.Timestamp(date_str)

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

        if not in_trade and i >= 20:
            dba_mask = dba_close.index <= date_ts
            m7 = dba_ma7.dropna().index <= date_ts
            m15 = dba_ma15.dropna().index <= date_ts
            if not dba_mask.any() or not m7.any() or not m15.any():
                continue

            dba_p = dba_close[dba_mask].iloc[-1]
            dba_7 = dba_ma7.dropna()[m7].iloc[-1]
            dba_15 = dba_ma15.dropna()[m15].iloc[-1]
            dba_rising = dba_p > dba_7 and dba_7 > dba_15

            vix_mask = vix.index <= date_ts
            if vix_mask.any() and vix[vix_mask].iloc[-1] > 40:
                continue

            wiki_rising = False
            if not wiki_ma7.empty and not wiki_ma21.empty:
                w7 = wiki_ma7.dropna().index <= date_ts
                w21 = wiki_ma21.dropna().index <= date_ts
                if w7.any() and w21.any():
                    wiki_rising = wiki_ma7.dropna()[w7].iloc[-1] > wiki_ma21.dropna()[w21].iloc[-1]

            if dba_rising:
                ticker = "GDX" if wiki_rising else "SLV"
            else:
                ticker = "SOXX" if not wiki_rising else "XLF"

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
