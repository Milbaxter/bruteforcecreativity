"""
Tech Subsector Catchup — buy the lagging tech sub-ETF when QQQ leads and rates drop.

Thesis: When QQQ rallies strongly (>2% in 5 days) and rates are falling (TLT up),
different tech sub-sectors rally at different speeds. Software (IGV) and cloud (SKYY)
are rate-sensitive and sometimes lag semiconductors (SOXX/SMH) or vice versa. The
lagging sub-sector catches up within 3-5 days as the broader tech rally broadens.

Three signals:
1. QQQ 5-day return > 1.5% (tech is in rally mode)
2. TLT 5-day return > 0% (rates supportive or at least not headwind)
3. One tech sub-ETF lags QQQ by > 1.5% over 5 days (catch-up opportunity)

Buy the tech sub-sector lagging the most. Sell after 5 days.
"""

import pandas as pd
import numpy as np

TECH_SUBS = ["IGV", "SOXX", "SKYY", "HACK", "ARKK"]

STRATEGY = {
    "name": "Tech Subsector Catchup",
    "hypothesis": "When QQQ rallies with rate support, lagging tech sub-sectors (IGV/SOXX/SKYY/HACK/ARKK) catch up within 3-5 days.",
    "universe": TECH_SUBS + ["QQQ", "TLT", "SPY"],
    "entry": "Buy most lagging tech sub-ETF when QQQ 5d > +1.5% AND TLT 5d > 0 AND sub-ETF lags QQQ by > 1.5%",
    "exit": "Sell after 5 days or +4%/-2% stop",
    "position_size": "80% of capital per trade",
    "eccentricity": "Tech sub-sector relative value with rate confirmation. Exploits uneven broadening of tech rallies across thematic ETFs.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    qqq = data_fetcher.get_prices("QQQ", start=start_date, end=end_date)
    tlt = data_fetcher.get_prices("TLT", start=start_date, end=end_date)

    if qqq.empty or tlt.empty:
        return

    qqq_close = qqq["Close"].dropna()
    tlt_close = tlt["Close"].dropna()
    qqq_close.index = pd.to_datetime(qqq_close.index)
    tlt_close.index = pd.to_datetime(tlt_close.index)

    # Fetch tech sub-sector ETFs
    sub_prices = {}
    for t in TECH_SUBS:
        df = data_fetcher.get_prices(t, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            sub_prices[t] = s

    if len(sub_prices) < 3:
        return

    # Common dates
    common = qqq_close.index.intersection(tlt_close.index)
    for s in sub_prices.values():
        common = common.intersection(s.index)
    if len(common) < 15:
        return
    common = common.sort_values()

    # Aligned data
    qqq_c = qqq_close.loc[common]
    tlt_c = tlt_close.loc[common]
    sub_matrix = pd.DataFrame({t: sub_prices[t].loc[common] for t in sub_prices})

    # Returns
    qqq_ret5 = qqq_c.pct_change(5)
    tlt_ret5 = tlt_c.pct_change(5)
    sub_ret5 = sub_matrix.pct_change(5)

    in_trade = False
    trade_ticker = None
    entry_price = None
    days_held = 0

    for i in range(10, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")

        if in_trade:
            days_held += 1
            current_price = float(sub_matrix[trade_ticker].iloc[i])
            pnl_pct = (current_price - entry_price) / entry_price

            if days_held >= 5 or pnl_pct >= 0.04 or pnl_pct <= -0.02:
                portfolio.sell(trade_ticker, all_shares=True, date=date_str)
                in_trade = False
                trade_ticker = None
                entry_price = None
                days_held = 0

        elif not in_trade:
            qr = float(qqq_ret5.iloc[i]) if pd.notna(qqq_ret5.iloc[i]) else 0
            tr = float(tlt_ret5.iloc[i]) if pd.notna(tlt_ret5.iloc[i]) else 0

            if qr <= 0.015 or tr <= 0:
                continue

            # Find most lagging sub-sector vs QQQ
            row = sub_ret5.iloc[i].dropna()
            if row.empty:
                continue

            gaps = row - qr  # negative = lagging QQQ
            worst_ticker = gaps.idxmin()
            worst_gap = float(gaps[worst_ticker])

            if worst_gap < -0.015:
                worst_price = float(sub_matrix[worst_ticker].iloc[i])
                result = portfolio.buy(worst_ticker, dollars=portfolio.cash * 0.8, date=date_str)
                if result:
                    in_trade = True
                    trade_ticker = worst_ticker
                    entry_price = worst_price
                    days_held = 0

    # Close remaining
    if in_trade:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(trade_ticker, all_shares=True, date=last_date)
