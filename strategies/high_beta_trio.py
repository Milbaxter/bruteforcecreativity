"""
High Beta Trio Rotation
Momentum rotation across three high-volatility, uncorrelated sector ETFs.
XOP (oil exploration), GDX (gold miners), KWEB (China tech).
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "High Beta Trio",
    "hypothesis": "XOP (oil exploration), GDX (gold miners), and KWEB (China tech) are high-beta "
                  "sector ETFs driven by completely different factors: oil prices, gold/real rates, "
                  "and Chinese policy. Their low correlation means one is usually trending while "
                  "others are flat or falling. 7-day momentum rotation every 3 days captures "
                  "whichever sector is currently trending. -4% stop loss limits damage from "
                  "sudden reversals. The volatility creates more rotation alpha than low-beta assets.",
    "universe": ["XOP", "GDX", "KWEB"],
    "entry": "Buy the ETF with highest 7-day momentum. Rotate every 3 trading days.",
    "exit": "Rotate to new momentum leader every 3 days, -4% stop loss per position",
    "position_size": "90% of capital in selected ETF",
    "eccentricity": "Oil exploration, gold miners, and China tech in one rotation — no institutional "
                    "allocation model would group these three together. They're from completely "
                    "different investment 'buckets' that never appear in the same portfolio.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    tickers = ["XOP", "GDX", "KWEB"]

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

    if len(common_idx) < 15:
        return

    closes = {t: price_data[t].loc[common_idx] for t in tickers}
    moms = {t: closes[t].pct_change(7) for t in tickers}

    trading_days = common_idx.tolist()

    current_holding = None
    entry_price = None
    last_rotation = -999

    for i in range(10, len(trading_days)):
        date = trading_days[i]
        date_str = date.strftime("%Y-%m-%d")

        # Stop loss
        if current_holding is not None and entry_price is not None:
            current = float(closes[current_holding].loc[date])
            pct = (current - entry_price) / entry_price
            if pct <= -0.04:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
                current_holding = None
                entry_price = None
                last_rotation = i
                continue

        # Rotate every 3 days
        if i - last_rotation < 3:
            continue

        mom_vals = {}
        for t in tickers:
            m = float(moms[t].loc[date]) if not pd.isna(moms[t].loc[date]) else -999
            mom_vals[t] = m

        target = max(mom_vals, key=mom_vals.get)

        if target != current_holding:
            if current_holding is not None:
                portfolio.sell(current_holding, all_shares=True, date=date_str)

            dollars = portfolio.cash * 0.90
            result = portfolio.buy(target, dollars=dollars, date=date_str)
            if result:
                current_holding = target
                entry_price = result["exec_price"]

        last_rotation = i
