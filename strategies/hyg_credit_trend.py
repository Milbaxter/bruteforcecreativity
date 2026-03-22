"""
HYG Credit Health Trend

Hypothesis: HYG (iShares High Yield Corporate Bond ETF) price trend directly
captures credit market health. When HYG is trending up, high-yield bonds are in
demand → credit conditions are healthy → risk-on. When HYG trends down, credit
is deteriorating → risk-off.

This is fundamentally different from HY SPREAD strategies:
- Spread = calculated HYG vs Treasury differential (noisy, depends on both legs)
- HYG price trend = direct market price action (simpler, cleaner signal)

Combined with Wikipedia "Credit_default_swap" or "Recession" attention as a
behavioral confirmation: rising fear-article attention during HYG decline
strengthens the risk-off signal.

Signals:
1. WHY: HYG price above/below its 7d and 15d MAs
2. WHEN: HYG rising → SOXX (risk-on growth); HYG falling → GDX (safety)
3. CONFIRMATION: Wikipedia recession attention direction refines asset selection
4. WHEN NOT: VIX > 40

Eccentricity: Using junk bond ETF price trend (not spread) as simple credit
barometer + Wikipedia recession attention for behavioral confirmation.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "HYG Credit Trend",
    "hypothesis": "HYG price trend captures credit health; rising HYG = risk-on (SOXX), falling HYG = risk-off (GDX/GLD).",
    "universe": ["SOXX", "GDX", "GLD", "XLF", "HYG"],
    "entry": "HYG uptrend: SOXX/XLF. HYG downtrend: GDX/GLD. Wiki recession attention picks within pair.",
    "exit": "Hold 5 days, reassess; -4% stop loss",
    "position_size": "70% of capital per trade",
    "eccentricity": "Junk bond ETF price trend (not spread) as credit signal + Wikipedia recession attention.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    hyg = data_fetcher.get_prices("HYG", start=start_date, end=end_date)
    if isinstance(hyg.columns, pd.MultiIndex):
        hyg.columns = hyg.columns.get_level_values(0)
    hyg_close = hyg["Close"].dropna()

    soxx = data_fetcher.get_prices("SOXX", start=start_date, end=end_date)
    if isinstance(soxx.columns, pd.MultiIndex):
        soxx.columns = soxx.columns.get_level_values(0)
    soxx_close = soxx["Close"].dropna()

    gdx = data_fetcher.get_prices("GDX", start=start_date, end=end_date)
    if isinstance(gdx.columns, pd.MultiIndex):
        gdx.columns = gdx.columns.get_level_values(0)
    gdx_close = gdx["Close"].dropna()

    gld = data_fetcher.get_prices("GLD", start=start_date, end=end_date)
    if isinstance(gld.columns, pd.MultiIndex):
        gld.columns = gld.columns.get_level_values(0)
    gld_close = gld["Close"].dropna()

    xlf = data_fetcher.get_prices("XLF", start=start_date, end=end_date)
    if isinstance(xlf.columns, pd.MultiIndex):
        xlf.columns = xlf.columns.get_level_values(0)
    xlf_close = xlf["Close"].dropna()

    vix = data_fetcher.get_vix(start=start_date, end=end_date)

    wiki_recession = data_fetcher.get_wikipedia_pageviews("Recession", start=start_date, end=end_date)

    if hyg_close.empty or soxx_close.empty:
        return

    hyg_ma7 = hyg_close.rolling(7).mean()
    hyg_ma15 = hyg_close.rolling(15).mean()

    wiki_ma7 = wiki_recession.rolling(7).mean() if not wiki_recession.empty else pd.Series(dtype=float)
    wiki_ma21 = wiki_recession.rolling(21).mean() if not wiki_recession.empty else pd.Series(dtype=float)

    close_map = {"SOXX": soxx_close, "GDX": gdx_close, "GLD": gld_close, "XLF": xlf_close}
    trading_days = soxx_close.index.strftime("%Y-%m-%d").tolist()

    in_trade = False
    trade_ticker = None
    entry_date = None
    entry_price = None

    for i, date_str in enumerate(trading_days):
        date_ts = pd.Timestamp(date_str)

        # Exit
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

        # Signal
        if not in_trade and i >= 20:
            hyg_mask = hyg_close.index <= date_ts
            m7_mask = hyg_ma7.dropna().index <= date_ts
            m15_mask = hyg_ma15.dropna().index <= date_ts
            if not hyg_mask.any() or not m7_mask.any() or not m15_mask.any():
                continue

            hyg_price = hyg_close[hyg_mask].iloc[-1]
            hyg_7 = hyg_ma7.dropna()[m7_mask].iloc[-1]
            hyg_15 = hyg_ma15.dropna()[m15_mask].iloc[-1]

            hyg_rising = hyg_price > hyg_7 and hyg_7 > hyg_15

            # VIX filter
            vix_mask = vix.index <= date_ts
            if vix_mask.any() and vix[vix_mask].iloc[-1] > 40:
                continue

            # Wiki recession trend
            wiki_rising = False
            if not wiki_ma7.empty and not wiki_ma21.empty:
                w7_mask = wiki_ma7.dropna().index <= date_ts
                w21_mask = wiki_ma21.dropna().index <= date_ts
                if w7_mask.any() and w21_mask.any():
                    wiki_rising = wiki_ma7.dropna()[w7_mask].iloc[-1] > wiki_ma21.dropna()[w21_mask].iloc[-1]

            # Asset selection
            if hyg_rising:
                # Credit healthy → growth
                ticker = "SOXX" if not wiki_rising else "XLF"
            else:
                # Credit stressed → safety
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
