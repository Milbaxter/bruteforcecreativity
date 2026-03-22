"""
TLT Volatility Regime

Hypothesis: Bond market volatility (proxied by TLT realized volatility) captures
rate uncertainty. When bond vol is HIGH, there's macro uncertainty about rates and
monetary policy. Gold miners (GDX) and gold (GLD) benefit as safe havens from rate
confusion. When bond vol is LOW, rates are stable and growth sectors (SOXX) thrive.

This is fundamentally different from TLT MOMENTUM (price direction):
- TLT momentum captures whether rates are rising or falling
- TLT VOLATILITY captures HOW UNCERTAIN the rate path is

Combined with Wikipedia "Federal_Reserve" attention for confirmation of macro focus.

Signals:
1. WHY: TLT 10-day realized volatility vs 30-day median
2. WHEN: High vol (> median * 1.3) → GDX/GLD; Low vol (< median * 0.7) → SOXX
3. CONFIRMATION: Wiki Fed attention direction for macro narrative
4. WHEN NOT: VIX > 40

Eccentricity: Bond volatility regime (not direction) as sector allocator + Wikipedia.
Most quants use bond direction, not vol-of-bonds.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "TLT Vol Regime",
    "hypothesis": "TLT realized volatility (bond market uncertainty) determines growth vs safety allocation, different from bond price direction.",
    "universe": ["GDX", "GLD", "SOXX", "XLF"],
    "entry": "High TLT vol: GDX/GLD (safety). Low TLT vol: SOXX (growth). Medium: XLF.",
    "exit": "Hold 5 days, reassess vol regime; -4% stop loss",
    "position_size": "70% of capital per trade",
    "eccentricity": "Bond VOLATILITY regime (not direction) as sector allocator. Using uncertainty itself as the signal.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    tlt = data_fetcher.get_prices("TLT", start=start_date, end=end_date)
    if isinstance(tlt.columns, pd.MultiIndex):
        tlt.columns = tlt.columns.get_level_values(0)
    tlt_close = tlt["Close"].dropna()

    gdx = data_fetcher.get_prices("GDX", start=start_date, end=end_date)
    if isinstance(gdx.columns, pd.MultiIndex):
        gdx.columns = gdx.columns.get_level_values(0)
    gdx_close = gdx["Close"].dropna()

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

    # Wikipedia Fed attention
    wiki_fed = data_fetcher.get_wikipedia_pageviews("Federal_Reserve", start=start_date, end=end_date)

    if tlt_close.empty or gdx_close.empty:
        return

    # Compute TLT realized volatility (10-day rolling std of daily returns, annualized)
    tlt_returns = tlt_close.pct_change().dropna()
    tlt_vol10 = tlt_returns.rolling(10).std() * np.sqrt(252)  # annualized
    tlt_vol30_median = tlt_vol10.rolling(30).median()

    # Wiki Fed rolling averages
    wiki_fed_ma7 = wiki_fed.rolling(7).mean() if not wiki_fed.empty else pd.Series(dtype=float)
    wiki_fed_ma21 = wiki_fed.rolling(21).mean() if not wiki_fed.empty else pd.Series(dtype=float)

    close_map = {"GDX": gdx_close, "GLD": gld_close, "SOXX": soxx_close, "XLF": xlf_close}
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

        # Signal computation
        if not in_trade and i >= 35:
            # TLT vol
            vol_mask = tlt_vol10.dropna().index <= date_ts
            med_mask = tlt_vol30_median.dropna().index <= date_ts
            if not vol_mask.any() or not med_mask.any():
                continue

            current_vol = tlt_vol10.dropna()[vol_mask].iloc[-1]
            median_vol = tlt_vol30_median.dropna()[med_mask].iloc[-1]

            if median_vol <= 0:
                continue

            vol_ratio = current_vol / median_vol

            # VIX filter
            vix_mask = vix.index <= date_ts
            if vix_mask.any() and vix[vix_mask].iloc[-1] > 40:
                continue

            # Wiki Fed trend (rising or falling)
            wiki_fed_rising = False
            if not wiki_fed_ma7.empty and not wiki_fed_ma21.empty:
                w7_mask = wiki_fed_ma7.dropna().index <= date_ts
                w21_mask = wiki_fed_ma21.dropna().index <= date_ts
                if w7_mask.any() and w21_mask.any():
                    wiki_fed_rising = wiki_fed_ma7.dropna()[w7_mask].iloc[-1] > wiki_fed_ma21.dropna()[w21_mask].iloc[-1]

            # Determine asset
            if vol_ratio > 1.3:
                # High bond vol → safety
                # If Fed wiki rising, GDX (miners benefit from policy attention)
                # Otherwise GLD (pure gold)
                ticker = "GDX" if wiki_fed_rising else "GLD"
            elif vol_ratio < 0.7:
                # Low bond vol → growth
                ticker = "SOXX"
            else:
                # Medium vol → neutral
                ticker = "XLF"

            close_s = close_map.get(ticker, gdx_close)
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
