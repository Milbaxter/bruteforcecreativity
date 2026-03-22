"""
TIPS + TLT Double Bond Matrix

Hypothesis: TIP (inflation-protected bonds) and TLT (long-term Treasury bonds) are
both bond markets but capture DIFFERENT things:
- TIP direction = inflation expectations (rising TIP = inflation fears)
- TLT direction = nominal rate expectations (rising TLT = rates falling)

Combining creates a 2x2 matrix of economic regimes:
1. TIP up + TLT up = flight to quality WITH inflation hedge → GDX (gold miners)
2. TIP up + TLT down = inflation rising, rates rising → SLV (industrial metal)
3. TIP down + TLT up = deflation scare, rates plunging → GLD (pure safety)
4. TIP down + TLT down = growth rally, no inflation → SOXX (tech growth)

Wikipedia "Inflation" or "Interest_rate" attention as tie-breaker.

Eccentricity: Using TWO bond market signals to create a 4-regime matrix.
Most strategies use a single bond signal; this captures the inflation vs rate nuance.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "TIPS TLT Bond Matrix",
    "hypothesis": "2x2 bond matrix from TIP (inflation) x TLT (rates) direction creates 4 distinct economic regimes for sector allocation.",
    "universe": ["GDX", "SLV", "GLD", "SOXX", "TIP", "TLT"],
    "entry": "TIP+TLT up: GDX. TIP up, TLT down: SLV. TIP down, TLT up: GLD. Both down: SOXX.",
    "exit": "Hold 5 days, reassess; -4% stop loss",
    "position_size": "70% of capital per trade",
    "eccentricity": "Double bond market regime matrix. Captures inflation vs rates nuance that single-signal strategies miss.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    tip = data_fetcher.get_prices("TIP", start=start_date, end=end_date)
    if isinstance(tip.columns, pd.MultiIndex):
        tip.columns = tip.columns.get_level_values(0)
    tip_close = tip["Close"].dropna()

    tlt = data_fetcher.get_prices("TLT", start=start_date, end=end_date)
    if isinstance(tlt.columns, pd.MultiIndex):
        tlt.columns = tlt.columns.get_level_values(0)
    tlt_close = tlt["Close"].dropna()

    gdx = data_fetcher.get_prices("GDX", start=start_date, end=end_date)
    if isinstance(gdx.columns, pd.MultiIndex):
        gdx.columns = gdx.columns.get_level_values(0)
    gdx_close = gdx["Close"].dropna()

    slv = data_fetcher.get_prices("SLV", start=start_date, end=end_date)
    if isinstance(slv.columns, pd.MultiIndex):
        slv.columns = slv.columns.get_level_values(0)
    slv_close = slv["Close"].dropna()

    gld = data_fetcher.get_prices("GLD", start=start_date, end=end_date)
    if isinstance(gld.columns, pd.MultiIndex):
        gld.columns = gld.columns.get_level_values(0)
    gld_close = gld["Close"].dropna()

    soxx = data_fetcher.get_prices("SOXX", start=start_date, end=end_date)
    if isinstance(soxx.columns, pd.MultiIndex):
        soxx.columns = soxx.columns.get_level_values(0)
    soxx_close = soxx["Close"].dropna()

    vix = data_fetcher.get_vix(start=start_date, end=end_date)

    if tip_close.empty or tlt_close.empty:
        return

    # MAs for TIP and TLT
    tip_ma7 = tip_close.rolling(7).mean()
    tip_ma15 = tip_close.rolling(15).mean()
    tlt_ma7 = tlt_close.rolling(7).mean()
    tlt_ma15 = tlt_close.rolling(15).mean()

    close_map = {"GDX": gdx_close, "SLV": slv_close, "GLD": gld_close, "SOXX": soxx_close}
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
            # TIP direction
            tip_mask = tip_close.index <= date_ts
            tip_7m = tip_ma7.dropna().index <= date_ts
            tip_15m = tip_ma15.dropna().index <= date_ts
            if not tip_mask.any() or not tip_7m.any() or not tip_15m.any():
                continue
            tip_p = tip_close[tip_mask].iloc[-1]
            tip_7 = tip_ma7.dropna()[tip_7m].iloc[-1]
            tip_15 = tip_ma15.dropna()[tip_15m].iloc[-1]
            tip_rising = tip_p > tip_7 and tip_7 > tip_15

            # TLT direction
            tlt_mask = tlt_close.index <= date_ts
            tlt_7m = tlt_ma7.dropna().index <= date_ts
            tlt_15m = tlt_ma15.dropna().index <= date_ts
            if not tlt_mask.any() or not tlt_7m.any() or not tlt_15m.any():
                continue
            tlt_p = tlt_close[tlt_mask].iloc[-1]
            tlt_7 = tlt_ma7.dropna()[tlt_7m].iloc[-1]
            tlt_15 = tlt_ma15.dropna()[tlt_15m].iloc[-1]
            tlt_rising = tlt_p > tlt_7 and tlt_7 > tlt_15

            # VIX filter
            vix_mask = vix.index <= date_ts
            if vix_mask.any() and vix[vix_mask].iloc[-1] > 40:
                continue

            # 2x2 matrix
            if tip_rising and tlt_rising:
                ticker = "GDX"  # Flight to quality + inflation hedge
            elif tip_rising and not tlt_rising:
                ticker = "SLV"  # Inflation rising, rates rising
            elif not tip_rising and tlt_rising:
                ticker = "GLD"  # Deflation scare
            else:
                ticker = "SOXX"  # Growth rally

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
