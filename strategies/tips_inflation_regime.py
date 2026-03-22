"""
TIPS Inflation Regime

Hypothesis: TIP (iShares TIPS Bond ETF) price direction captures market inflation
expectations. When TIP is trending up, the market expects rising inflation, which
benefits commodities (GDX, SLV). When TIP is trending down, inflation expectations
are falling, which benefits growth (SOXX) and financials.

Combined with Wikipedia "Inflation" pageviews: when attention to inflation is high
AND TIPS are rising, the inflation narrative has legs. When TIPS are falling and
inflation attention is dropping, the narrative is fading.

Signals:
1. WHY: TIP 7-day momentum direction
2. WHEN: TIP > 7d MA = inflation rising; TIP < 7d MA = disinflation
3. ASSET: Rising inflation → GDX or SLV; Falling → SOXX or XLF
4. CONFIRMATION: Wiki "Inflation" attention direction picks between paired assets
5. Rotate every 5 days

Eccentricity: TIPS-based inflation regime combined with Wikipedia inflation attention.
Most strategies use CPI or breakeven rates, not TIPS price action + Wikipedia.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "TIPS Inflation Regime",
    "hypothesis": "TIP price direction captures inflation expectations; rising TIPS favor commodities, falling TIPS favor growth.",
    "universe": ["GDX", "SLV", "SOXX", "XLF", "TIP"],
    "entry": "TIP rising + wiki inflation up: GDX. TIP rising: SLV. TIP falling + wiki down: SOXX. TIP falling: XLF.",
    "exit": "Hold 5 days, reassess; -4% stop loss",
    "position_size": "70% of capital per trade",
    "eccentricity": "TIPS price action as inflation regime signal + Wikipedia inflation attention for narrative confirmation.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    tip = data_fetcher.get_prices("TIP", start=start_date, end=end_date)
    if isinstance(tip.columns, pd.MultiIndex):
        tip.columns = tip.columns.get_level_values(0)
    tip_close = tip["Close"].dropna()

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

    # Wikipedia inflation attention
    wiki_inflation = data_fetcher.get_wikipedia_pageviews("Inflation", start=start_date, end=end_date)

    if tip_close.empty or gdx_close.empty:
        return

    # TIP 7-day and 15-day MAs
    tip_ma7 = tip_close.rolling(7).mean()
    tip_ma15 = tip_close.rolling(15).mean()

    # Wiki inflation MAs
    wiki_ma7 = wiki_inflation.rolling(7).mean() if not wiki_inflation.empty else pd.Series(dtype=float)
    wiki_ma21 = wiki_inflation.rolling(21).mean() if not wiki_inflation.empty else pd.Series(dtype=float)

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
            # TIP direction: above 7d MA AND 7d MA > 15d MA = rising
            tip_mask7 = tip_ma7.dropna().index <= date_ts
            tip_mask15 = tip_ma15.dropna().index <= date_ts
            if not tip_mask7.any() or not tip_mask15.any():
                continue

            tip_price = tip_close[tip_close.index <= date_ts].iloc[-1]
            tip_7 = tip_ma7.dropna()[tip_mask7].iloc[-1]
            tip_15 = tip_ma15.dropna()[tip_mask15].iloc[-1]

            tip_rising = tip_price > tip_7 and tip_7 > tip_15

            # VIX filter
            vix_mask = vix.index <= date_ts
            if vix_mask.any() and vix[vix_mask].iloc[-1] > 40:
                continue

            # Wiki inflation trend
            wiki_rising = False
            if not wiki_ma7.empty and not wiki_ma21.empty:
                w7_mask = wiki_ma7.dropna().index <= date_ts
                w21_mask = wiki_ma21.dropna().index <= date_ts
                if w7_mask.any() and w21_mask.any():
                    wiki_rising = wiki_ma7.dropna()[w7_mask].iloc[-1] > wiki_ma21.dropna()[w21_mask].iloc[-1]

            # Asset selection
            if tip_rising:
                # Inflation regime → commodities
                ticker = "GDX" if wiki_rising else "SLV"
            else:
                # Disinflation regime → growth
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
