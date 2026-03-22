"""
TIPS + Crypto Fear Double Signal

Hypothesis: TIPS (TIP ETF) direction captures inflation expectations, while
crypto fear/greed captures cross-market risk sentiment. Combining them:

1. TIP rising + crypto fear (<40): Real inflation fear across markets → GDX (gold miners)
2. TIP rising + crypto neutral/greed (>=40): Inflation narrative without panic → SLV
3. TIP falling + crypto fear (<40): Deflation + risk-off → GLD (pure gold safety)
4. TIP falling + crypto greed (>=40): Disinflation + risk-on → SOXX (tech growth)

The TIPS signal proved robust in walk-forward (3/3 windows). Adding crypto
fear as cross-domain confirmation should maintain that robustness while
improving asset selection.

Eccentricity: Inflation-protected bond direction + crypto market sentiment =
two completely independent markets providing a unified allocation signal.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "TIPS Crypto Fear Signal",
    "hypothesis": "TIPS direction (inflation) + crypto fear/greed (risk sentiment) creates a 2x2 regime for GDX/SLV/GLD/SOXX.",
    "universe": ["GDX", "SLV", "GLD", "SOXX", "TIP"],
    "entry": "TIP up + fear: GDX. TIP up + greed: SLV. TIP down + fear: GLD. TIP down + greed: SOXX.",
    "exit": "Hold 5 days, reassess; -4% stop loss",
    "position_size": "70% of capital per trade",
    "eccentricity": "TIPS bond direction + crypto sentiment cross-domain double confirmation.",
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

    gld = data_fetcher.get_prices("GLD", start=start_date, end=end_date)
    if isinstance(gld.columns, pd.MultiIndex):
        gld.columns = gld.columns.get_level_values(0)
    gld_close = gld["Close"].dropna()

    soxx = data_fetcher.get_prices("SOXX", start=start_date, end=end_date)
    if isinstance(soxx.columns, pd.MultiIndex):
        soxx.columns = soxx.columns.get_level_values(0)
    soxx_close = soxx["Close"].dropna()

    vix = data_fetcher.get_vix(start=start_date, end=end_date)
    crypto_fg = data_fetcher.get_crypto_fear_greed(days=500)

    if tip_close.empty or gdx_close.empty or crypto_fg.empty:
        return

    tip_ma7 = tip_close.rolling(7).mean()
    tip_ma15 = tip_close.rolling(15).mean()

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

            # Crypto fear/greed
            fg_mask = crypto_fg.index <= date_ts
            if not fg_mask.any():
                continue
            fg_val = crypto_fg[fg_mask].iloc[-1]
            is_fear = fg_val < 40

            # VIX filter
            vix_mask = vix.index <= date_ts
            if vix_mask.any() and vix[vix_mask].iloc[-1] > 40:
                continue

            # 2x2 matrix
            if tip_rising and is_fear:
                ticker = "GDX"
            elif tip_rising and not is_fear:
                ticker = "SLV"
            elif not tip_rising and is_fear:
                ticker = "GLD"
            else:
                ticker = "SOXX"

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
