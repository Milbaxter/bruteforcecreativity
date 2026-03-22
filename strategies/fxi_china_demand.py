"""
FXI China Demand Direction

Hypothesis: FXI (iShares China Large-Cap ETF) direction captures China's economic
momentum, which drives global commodity demand and supply chain dynamics:

- FXI rising: China demand strong → commodity exporters benefit → GDX/SLV
- FXI falling: China demand weakening → commodities soft, US growth relatively better → SOXX

China is the world's largest consumer of copper, iron, and many raw materials.
When FXI trends up, it signals the global commodity demand engine is running.

Combined with Wikipedia "Tariff" attention: rising tariff attention during FXI
decline signals trade war risk → stronger safety signal.

Signals:
1. WHY: FXI 7d/15d MA trend direction
2. WHEN: FXI rising → GDX/SLV; FXI falling → SOXX/XLF
3. CONFIRMATION: Wiki tariff attention for trade risk narrative
4. WHEN NOT: VIX > 40
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "FXI China Demand",
    "hypothesis": "FXI China large-cap direction captures global commodity demand dynamics for sector allocation.",
    "universe": ["GDX", "SLV", "SOXX", "XLF", "FXI"],
    "entry": "FXI up + tariff wiki calm: GDX. FXI up: SLV. FXI down + tariff wiki up: GLD→GDX. FXI down: SOXX.",
    "exit": "Hold 5 days, reassess; -4% stop loss",
    "position_size": "70% of capital per trade",
    "eccentricity": "China large-cap ETF as global demand thermometer + Wikipedia tariff attention for trade risk.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    fxi = data_fetcher.get_prices("FXI", start=start_date, end=end_date)
    if isinstance(fxi.columns, pd.MultiIndex):
        fxi.columns = fxi.columns.get_level_values(0)
    fxi_close = fxi["Close"].dropna()

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
    wiki = data_fetcher.get_wikipedia_pageviews("Tariff", start=start_date, end=end_date)

    if fxi_close.empty or gdx_close.empty:
        return

    fxi_ma7 = fxi_close.rolling(7).mean()
    fxi_ma15 = fxi_close.rolling(15).mean()
    wiki_ma7 = wiki.rolling(7).mean() if not wiki.empty else pd.Series(dtype=float)
    wiki_ma21 = wiki.rolling(21).mean() if not wiki.empty else pd.Series(dtype=float)

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
            fxi_mask = fxi_close.index <= date_ts
            m7 = fxi_ma7.dropna().index <= date_ts
            m15 = fxi_ma15.dropna().index <= date_ts
            if not fxi_mask.any() or not m7.any() or not m15.any():
                continue

            fxi_p = fxi_close[fxi_mask].iloc[-1]
            fxi_7 = fxi_ma7.dropna()[m7].iloc[-1]
            fxi_15 = fxi_ma15.dropna()[m15].iloc[-1]
            fxi_rising = fxi_p > fxi_7 and fxi_7 > fxi_15

            vix_mask = vix.index <= date_ts
            if vix_mask.any() and vix[vix_mask].iloc[-1] > 40:
                continue

            wiki_rising = False
            if not wiki_ma7.empty and not wiki_ma21.empty:
                w7 = wiki_ma7.dropna().index <= date_ts
                w21 = wiki_ma21.dropna().index <= date_ts
                if w7.any() and w21.any():
                    wiki_rising = wiki_ma7.dropna()[w7].iloc[-1] > wiki_ma21.dropna()[w21].iloc[-1]

            if fxi_rising:
                # China demand strong → commodities
                ticker = "GDX" if not wiki_rising else "SLV"
            else:
                # China weak → US domestic, but tariff fear → gold miners
                ticker = "GDX" if wiki_rising else "SOXX"

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
