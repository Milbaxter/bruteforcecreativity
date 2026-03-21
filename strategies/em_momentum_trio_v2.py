"""
Emerging Markets Momentum Trio v2
Enhanced version: 5-day lookback, 20-day MA trend filter, 3% stop loss.
Only buy the leader if it's above its 20-day MA (confirmed uptrend).
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "EM Momentum Trio v2",
    "hypothesis": "Country momentum with trend confirmation: only rotate into the 5-day leader if it's above its 20-day MA. This filters out mean-reversion traps where a country ETF has short-term momentum but is in a downtrend.",
    "universe": ["EWZ", "INDA", "EWT"],
    "entry": "Buy strongest 5-day momentum country ETF IF above 20-day MA. Rotate every 3 days.",
    "exit": "Rotate to new leader, -3% stop loss, or hold current if no qualified leader",
    "position_size": "90% of capital in selected ETF",
    "eccentricity": "Dual-filtered country momentum — short-term signal confirmed by medium-term trend in emerging markets too small for institutional country allocation mandates",
}


def run(data_fetcher, portfolio, start_date, end_date):
    tickers = ["EWZ", "INDA", "EWT"]

    price_data = {}
    for ticker in tickers:
        df = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if not df.empty:
            price_data[ticker] = df["Close"]

    if len(price_data) < 3:
        return

    common_idx = price_data[tickers[0]].index
    for t in tickers[1:]:
        common_idx = common_idx.intersection(price_data[t].index)

    closes = {t: price_data[t].loc[common_idx] for t in tickers}
    moms = {t: closes[t].pct_change(5) for t in tickers}
    ma20 = {t: closes[t].rolling(20).mean() for t in tickers}

    trading_days = common_idx.tolist()

    current_holding = None
    entry_price = None
    last_rotation = -999

    for i in range(25, len(trading_days)):
        date = trading_days[i]
        date_str = date.strftime("%Y-%m-%d")

        # Stop loss check
        if current_holding is not None and entry_price is not None:
            current = float(closes[current_holding].loc[date])
            pct = (current - entry_price) / entry_price
            if pct <= -0.03:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
                current_holding = None
                entry_price = None
                last_rotation = i
                continue

        # Rotate every 3 days
        if i - last_rotation < 3:
            continue

        # Get momentums and trend filter
        candidates = {}
        for t in tickers:
            m = float(moms[t].loc[date]) if not pd.isna(moms[t].loc[date]) else -999
            ma_val = float(ma20[t].loc[date]) if not pd.isna(ma20[t].loc[date]) else 0
            price = float(closes[t].loc[date])

            # Only consider if above 20-day MA (confirmed uptrend)
            if price > ma_val:
                candidates[t] = m

        if not candidates:
            # No qualified candidate — sell current and wait
            if current_holding is not None:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
                current_holding = None
                entry_price = None
            last_rotation = i
            continue

        target = max(candidates, key=candidates.get)

        if target != current_holding:
            if current_holding is not None:
                portfolio.sell(current_holding, all_shares=True, date=date_str)

            dollars = portfolio.cash * 0.90
            result = portfolio.buy(target, dollars=dollars, date=date_str)
            if result:
                current_holding = target
                entry_price = result["exec_price"]

        last_rotation = i
