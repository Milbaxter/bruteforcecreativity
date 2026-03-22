"""
FRED Multi-Factor Macro Composite

Hypothesis: A composite score from multiple FRED macro series captures the overall
economic regime better than any single indicator. By combining yield curve (T10Y2Y),
high-yield credit spread (BAMLH0A0HYM2), dollar index trend, and VIX direction,
we get a robust risk-on/risk-off signal.

Each factor contributes +1 (expansion) or -1 (contraction):
- T10Y2Y steepening (5d positive change): +1
- HY spread tightening (5d negative change): +1
- Dollar weakening (DXY/UUP falling): +1
- VIX declining: +1

Score 3-4: Strong risk-on → SOXX
Score 1-2: Moderate → XLF
Score -1 to 0: Cautious → GLD
Score -2 to -4: Risk-off → GDX (leveraged safe haven)

Different from existing strategies because it uses 4 independent FRED-derived
factors in a composite, not any single regime signal.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "FRED Macro Composite",
    "hypothesis": "4-factor FRED macro composite score (yield curve + credit + dollar + VIX) determines optimal sector allocation.",
    "universe": ["SOXX", "XLF", "GLD", "GDX"],
    "entry": "Score 3-4: SOXX. Score 1-2: XLF. Score -1 to 0: GLD. Score -2 to -4: GDX.",
    "exit": "Hold 5 days then reassess composite score; -4% stop loss",
    "position_size": "70% of capital per trade",
    "eccentricity": "Multi-factor macro composite from diverse FRED data. No single-indicator weakness.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Fetch tradeable assets
    soxx = data_fetcher.get_prices("SOXX", start=start_date, end=end_date)
    if isinstance(soxx.columns, pd.MultiIndex):
        soxx.columns = soxx.columns.get_level_values(0)
    soxx_close = soxx["Close"].dropna()

    xlf = data_fetcher.get_prices("XLF", start=start_date, end=end_date)
    if isinstance(xlf.columns, pd.MultiIndex):
        xlf.columns = xlf.columns.get_level_values(0)
    xlf_close = xlf["Close"].dropna()

    gld = data_fetcher.get_prices("GLD", start=start_date, end=end_date)
    if isinstance(gld.columns, pd.MultiIndex):
        gld.columns = gld.columns.get_level_values(0)
    gld_close = gld["Close"].dropna()

    gdx = data_fetcher.get_prices("GDX", start=start_date, end=end_date)
    if isinstance(gdx.columns, pd.MultiIndex):
        gdx.columns = gdx.columns.get_level_values(0)
    gdx_close = gdx["Close"].dropna()

    # Fetch macro data
    t10y2y = data_fetcher.get_fred_series("T10Y2Y", start=start_date, end=end_date)
    hy_spread = data_fetcher.get_fred_series("BAMLH0A0HYM2", start=start_date, end=end_date)
    vix = data_fetcher.get_vix(start=start_date, end=end_date)

    # Dollar proxy: UUP ETF
    uup = data_fetcher.get_prices("UUP", start=start_date, end=end_date)
    if isinstance(uup.columns, pd.MultiIndex):
        uup.columns = uup.columns.get_level_values(0)
    uup_close = uup["Close"].dropna() if not uup.empty else pd.Series(dtype=float)

    if soxx_close.empty or t10y2y.empty:
        return

    # Reference trading days from SOXX
    trading_days = soxx_close.index.strftime("%Y-%m-%d").tolist()

    close_map = {
        "SOXX": soxx_close,
        "XLF": xlf_close,
        "GLD": gld_close,
        "GDX": gdx_close,
    }

    in_trade = False
    trade_ticker = None
    entry_date = None
    entry_price = None
    prev_score = None

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

                if pct_change <= -4.0:
                    portfolio.sell(trade_ticker, all_shares=True, date=date_str)
                    in_trade = False
                    trade_ticker = None
                    entry_date = None
                    entry_price = None
                    continue

                if days_held >= 5:
                    portfolio.sell(trade_ticker, all_shares=True, date=date_str)
                    in_trade = False
                    trade_ticker = None
                    entry_date = None
                    entry_price = None
                    # Fall through to reenter

        # Compute composite score
        if i >= 10 and not in_trade:
            score = 0

            # Factor 1: T10Y2Y direction (5d change)
            t_mask = t10y2y.index <= date_ts
            if t_mask.any():
                recent_t = t10y2y[t_mask]
                if len(recent_t) >= 6:
                    t_chg = recent_t.iloc[-1] - recent_t.iloc[-6]
                    score += 1 if t_chg > 0 else -1

            # Factor 2: HY spread direction (5d change, tightening = good)
            hy_mask = hy_spread.index <= date_ts
            if hy_mask.any():
                recent_hy = hy_spread[hy_mask]
                if len(recent_hy) >= 6:
                    hy_chg = recent_hy.iloc[-1] - recent_hy.iloc[-6]
                    score += 1 if hy_chg < 0 else -1  # Tightening = positive

            # Factor 3: Dollar direction (5d, weakening = positive for risk)
            if not uup_close.empty:
                uup_mask = uup_close.index <= date_ts
                if uup_mask.any():
                    recent_uup = uup_close[uup_mask]
                    if len(recent_uup) >= 6:
                        uup_chg = (recent_uup.iloc[-1] - recent_uup.iloc[-6]) / recent_uup.iloc[-6]
                        score += 1 if uup_chg < 0 else -1

            # Factor 4: VIX direction (5d, declining = positive)
            vix_mask = vix.index <= date_ts
            if vix_mask.any():
                recent_vix = vix[vix_mask]
                if len(recent_vix) >= 6:
                    vix_chg = recent_vix.iloc[-1] - recent_vix.iloc[-6]
                    score += 1 if vix_chg < 0 else -1

            # Map score to asset
            if score >= 3:
                ticker = "SOXX"
            elif score >= 1:
                ticker = "XLF"
            elif score >= -1:
                ticker = "GLD"
            else:
                ticker = "GDX"

            # Don't enter same position as last
            if ticker == trade_ticker and prev_score == score:
                continue

            close_s = close_map.get(ticker, soxx_close)
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
                    prev_score = score

    if in_trade and trade_ticker:
        portfolio.sell(trade_ticker, all_shares=True, date=trading_days[-1])
