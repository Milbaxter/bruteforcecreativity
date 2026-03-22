"""
Commodity Index Direction

Hypothesis: Broad commodity index (GSG - iShares S&P GSCI) direction captures the
inflation/growth cycle better than any single commodity. Rising GSG = rising commodity
prices = inflation + global demand = buy commodity producers (GDX, SLV). Falling GSG =
falling commodities = disinflation/recession risk = buy growth tech (SOXX).

Combined with crypto fear/greed for cross-domain confirmation: crypto fear during
rising commodities means REAL inflation fear (not just speculation), strengthening
the commodity signal.

Signals:
1. WHY: GSG 7-day momentum direction (above/below 7d and 15d MAs)
2. WHEN: GSG rising = inflation trade (GDX/SLV); GSG falling = disinflation (SOXX/XLF)
3. CONFIRMATION: Crypto fear favors GDX over SLV; crypto greed favors SOXX over XLF
4. WHEN NOT: VIX > 40

Eccentricity: Using a broad commodity basket as sector allocation signal + crypto
sentiment cross-domain. Commodity index direction is underused vs individual commodities.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Commodity Index Direction",
    "hypothesis": "GSG commodity index direction captures inflation cycle; combined with crypto sentiment for sector selection.",
    "universe": ["GDX", "SLV", "SOXX", "XLF", "GSG"],
    "entry": "GSG rising + crypto fear: GDX. GSG rising: SLV. GSG falling + crypto greed: SOXX. GSG falling: XLF.",
    "exit": "Hold 5 days, reassess; -4% stop loss",
    "position_size": "70% of capital per trade",
    "eccentricity": "Broad commodity index as inflation regime signal + crypto fear/greed as narrative confirmation.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    gsg = data_fetcher.get_prices("GSG", start=start_date, end=end_date)
    if isinstance(gsg.columns, pd.MultiIndex):
        gsg.columns = gsg.columns.get_level_values(0)
    gsg_close = gsg["Close"].dropna()

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
    crypto_fg = data_fetcher.get_crypto_fear_greed(days=500)

    if gsg_close.empty or gdx_close.empty:
        return

    gsg_ma7 = gsg_close.rolling(7).mean()
    gsg_ma15 = gsg_close.rolling(15).mean()

    close_map = {"GDX": gdx_close, "SLV": slv_close, "SOXX": soxx_close, "XLF": xlf_close}
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
            gsg_mask = gsg_close.index <= date_ts
            m7_mask = gsg_ma7.dropna().index <= date_ts
            m15_mask = gsg_ma15.dropna().index <= date_ts
            if not gsg_mask.any() or not m7_mask.any() or not m15_mask.any():
                continue

            gsg_price = gsg_close[gsg_mask].iloc[-1]
            gsg_7 = gsg_ma7.dropna()[m7_mask].iloc[-1]
            gsg_15 = gsg_ma15.dropna()[m15_mask].iloc[-1]

            commodities_rising = gsg_price > gsg_7 and gsg_7 > gsg_15

            # VIX
            vix_mask = vix.index <= date_ts
            if vix_mask.any() and vix[vix_mask].iloc[-1] > 40:
                continue

            # Crypto
            fg_val = 50
            fg_mask = crypto_fg.index <= date_ts
            if fg_mask.any():
                fg_val = crypto_fg[fg_mask].iloc[-1]

            # Asset selection
            if commodities_rising:
                ticker = "GDX" if fg_val < 40 else "SLV"
            else:
                ticker = "SOXX" if fg_val > 50 else "XLF"

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
