"""
BTC-TLT Divergence — trade equity index when Bitcoin and bonds send conflicting signals.

Thesis: BTC is a risk-on asset; TLT is a risk-off asset. When both move strongly in
the SAME direction simultaneously, it's noise/confusion. But when they diverge sharply
(BTC up + TLT down = clear risk-on; BTC down + TLT up = clear risk-off), the signal
is much stronger. Trade QQQ (most risk-sensitive large cap index) in the direction
of the consensus signal, with a quick 3-5 day hold.

Three signals:
1. BTC 5-day return and TLT 5-day return have opposite signs AND both > 2% magnitude
2. QQQ hasn't fully priced the signal (QQQ 5-day return is lagging the risk direction)
3. Confirmed by VIX direction (VIX falling = risk-on confirmation, rising = risk-off)

Eccentricity: Using crypto-bond divergence as a risk regime signal for equity timing.
No one trades QQQ based on BTC-TLT spreads. The cross-asset signal is genuinely novel.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "BTC TLT Divergence",
    "hypothesis": "When BTC (risk-on) and TLT (risk-off) diverge sharply, the risk signal is clear but QQQ lags. Buy QQQ on risk-on divergence (BTC up + TLT down + QQQ lagging); sit out on risk-off.",
    "universe": ["QQQ", "TLT", "BTC-USD", "SPY"],
    "entry": "Buy QQQ when BTC 5d return > +2% AND TLT 5d return < -1% AND QQQ 5d return < BTC 5d return AND VIX falling",
    "exit": "Sell after 5 days or +3%/-2% stop",
    "position_size": "85% of capital per trade",
    "eccentricity": "Crypto-bond divergence as equity timing signal. Cross-asset class consensus detection. No institution would combine BTC and TLT to trade QQQ.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    btc = data_fetcher.get_prices("BTC-USD", start=start_date, end=end_date)
    tlt = data_fetcher.get_prices("TLT", start=start_date, end=end_date)
    qqq = data_fetcher.get_prices("QQQ", start=start_date, end=end_date)
    vix = data_fetcher.get_vix(start=start_date, end=end_date)

    if btc.empty or tlt.empty or qqq.empty or vix.empty:
        return

    btc_close = btc["Close"].dropna()
    tlt_close = tlt["Close"].dropna()
    qqq_close = qqq["Close"].dropna()

    # Align to common trading dates (BTC trades every day, equities weekdays only)
    btc_close.index = pd.to_datetime(btc_close.index)
    tlt_close.index = pd.to_datetime(tlt_close.index)
    qqq_close.index = pd.to_datetime(qqq_close.index)
    vix.index = pd.to_datetime(vix.index)

    # Use QQQ trading days as the base
    common = qqq_close.index.intersection(tlt_close.index).intersection(vix.index)

    # Reindex BTC to trading days (forward fill weekend gaps)
    btc_aligned = btc_close.reindex(common, method="ffill")

    if len(common) < 15:
        return

    qqq_c = qqq_close.loc[common]
    tlt_c = tlt_close.loc[common]
    btc_c = btc_aligned.loc[common]
    vix_c = vix.loc[common]

    # 5-day returns
    btc_ret5 = btc_c.pct_change(5)
    tlt_ret5 = tlt_c.pct_change(5)
    qqq_ret5 = qqq_c.pct_change(5)
    vix_change5 = vix_c.diff(5)

    in_trade = False
    entry_price = None
    days_held = 0

    for i in range(10, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        price = float(qqq_c.iloc[i])

        if in_trade:
            days_held += 1
            pnl_pct = (price - entry_price) / entry_price

            if days_held >= 5 or pnl_pct >= 0.03 or pnl_pct <= -0.02:
                portfolio.sell("QQQ", all_shares=True, date=date_str)
                in_trade = False
                entry_price = None
                days_held = 0

        elif not in_trade:
            br = float(btc_ret5.iloc[i]) if pd.notna(btc_ret5.iloc[i]) else 0
            tr = float(tlt_ret5.iloc[i]) if pd.notna(tlt_ret5.iloc[i]) else 0
            qr = float(qqq_ret5.iloc[i]) if pd.notna(qqq_ret5.iloc[i]) else 0
            vc = float(vix_change5.iloc[i]) if pd.notna(vix_change5.iloc[i]) else 0

            # Risk-ON signal: BTC up, TLT down, QQQ lagging, VIX falling
            if br > 0.02 and tr < -0.01 and qr < br and vc < 0:
                result = portfolio.buy("QQQ", dollars=portfolio.cash * 0.85, date=date_str)
                if result:
                    in_trade = True
                    entry_price = price
                    days_held = 0

    # Close remaining
    if in_trade:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell("QQQ", all_shares=True, date=last_date)
