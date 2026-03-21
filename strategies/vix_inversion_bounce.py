"""
VIX Inversion Bounce — buy SPY when VIX term structure inverts + oversold.

Thesis: When VIX (spot) trades above VIX3M (3-month VIX), the term structure is
"inverted" — meaning near-term fear exceeds long-term fear. This is a panic signal that
historically resolves within 3-7 days as fear normalizes. Combined with SPY being oversold
(RSI < 35, 3-day drawdown > 2%), we get a high-probability mean reversion setup.

Three signals:
1. VIX/VIX3M ratio > 1.05 (term structure inverted by >5%)
2. SPY 3-day return < -2% (short-term oversold)
3. SPY RSI(14) < 35 (momentum oversold confirmation)

Eccentricity: Uses VIX term structure (not just VIX level) as the primary signal.
Most retail traders watch VIX level; the term structure ratio is a more nuanced
institutional signal that we combine with simple oversold filters.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "VIX Inversion Bounce",
    "hypothesis": "VIX term structure inversion (VIX > VIX3M by >5%) signals panic that resolves in 3-7 days. Buy SPY when inverted + SPY oversold on 3-day drawdown + RSI < 35.",
    "universe": ["SPY", "^VIX", "^VIX3M"],
    "entry": "Buy SPY when VIX/VIX3M > 1.05 AND SPY 3-day return < -2% AND RSI(14) < 35",
    "exit": "Sell after 5 days or +3%/-2% stop",
    "position_size": "90% of capital per trade",
    "eccentricity": "VIX term structure analysis (not just VIX level) as panic indicator. Cross-derivative signal for equity entry timing.",
}


def compute_rsi(prices, period=14):
    """Compute RSI from price series."""
    delta = prices.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def run(data_fetcher, portfolio, start_date, end_date):
    # Fetch VIX spot and VIX3M (3-month VIX)
    vix = data_fetcher.get_vix(start=start_date, end=end_date)
    vix3m_df = data_fetcher.get_prices("^VIX3M", start=start_date, end=end_date)
    spy = data_fetcher.get_prices("SPY", start=start_date, end=end_date)

    if spy.empty or vix.empty or vix3m_df.empty:
        return

    spy_close = spy["Close"].dropna()
    vix3m = vix3m_df["Close"].dropna() if "Close" in vix3m_df.columns else pd.Series(dtype=float)

    if vix3m.empty:
        return

    # Align all to common dates
    vix.index = pd.to_datetime(vix.index)
    vix3m.index = pd.to_datetime(vix3m.index)
    spy_close.index = pd.to_datetime(spy_close.index)

    common = vix.index.intersection(vix3m.index).intersection(spy_close.index)
    if len(common) < 20:
        return

    vix_c = vix.loc[common]
    vix3m_c = vix3m.loc[common]
    spy_c = spy_close.loc[common]

    # Compute signals
    vix_ratio = vix_c / vix3m_c  # > 1 = inverted
    spy_ret_3d = spy_c.pct_change(3)
    spy_rsi = compute_rsi(spy_c, 14)

    in_trade = False
    entry_price = None
    days_held = 0

    for i in range(20, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        price = float(spy_c.iloc[i])

        if in_trade:
            days_held += 1
            pnl_pct = (price - entry_price) / entry_price

            if days_held >= 5 or pnl_pct >= 0.03 or pnl_pct <= -0.02:
                portfolio.sell("SPY", all_shares=True, date=date_str)
                in_trade = False
                entry_price = None
                days_held = 0

        elif not in_trade:
            ratio = float(vix_ratio.iloc[i]) if pd.notna(vix_ratio.iloc[i]) else 0
            ret3d = float(spy_ret_3d.iloc[i]) if pd.notna(spy_ret_3d.iloc[i]) else 0
            rsi = float(spy_rsi.iloc[i]) if pd.notna(spy_rsi.iloc[i]) else 50

            # Entry: VIX inverted + SPY oversold + low RSI
            if ratio > 1.05 and ret3d < -0.02 and rsi < 35:
                result = portfolio.buy("SPY", dollars=portfolio.cash * 0.9, date=date_str)
                if result:
                    in_trade = True
                    entry_price = price
                    days_held = 0

    # Close remaining
    if in_trade:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell("SPY", all_shares=True, date=last_date)
