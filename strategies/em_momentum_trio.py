"""
Emerging Markets Momentum Trio
Momentum rotation across Brazil, India, and Taiwan country ETFs.
These three represent different EM economies with low correlation.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Emerging Markets Momentum Trio",
    "hypothesis": "Brazil (commodity exporter), India (domestic consumption), and Taiwan (semiconductor supply chain) have low correlation and strong individual trends. Short-term momentum rotation at 3-day frequency captures country-level flows before they reverse.",
    "universe": ["EWZ", "INDA", "EWT"],
    "entry": "Buy the country ETF with strongest 7-day momentum. Rotate every 3 trading days.",
    "exit": "Rotate to new leader every 3 days, -4% stop loss per position",
    "position_size": "90% of capital in selected ETF",
    "eccentricity": "Country-level momentum rotation at 3-day frequency — institutions do country allocation quarterly, this catches short-term EM capital flows too small for institutional mandates",
}


def run(data_fetcher, portfolio, start_date, end_date):
    tickers = ["EWZ", "INDA", "EWT"]

    # Fetch prices for all three
    price_data = {}
    for ticker in tickers:
        df = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if not df.empty:
            price_data[ticker] = df["Close"]

    if len(price_data) < 3:
        return

    # Align indices
    common_idx = price_data[tickers[0]].index
    for t in tickers[1:]:
        common_idx = common_idx.intersection(price_data[t].index)

    closes = {t: price_data[t].loc[common_idx] for t in tickers}

    # 7-day momentum
    moms = {t: closes[t].pct_change(7) for t in tickers}

    trading_days = common_idx.tolist()

    current_holding = None
    entry_price = None
    last_rotation = -999

    for i in range(10, len(trading_days)):
        date = trading_days[i]
        date_str = date.strftime("%Y-%m-%d")

        # Stop loss check
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

        # Get momentums
        mom_vals = {}
        for t in tickers:
            m = float(moms[t].loc[date]) if not pd.isna(moms[t].loc[date]) else -999
            mom_vals[t] = m

        # Pick the strongest momentum
        target = max(mom_vals, key=mom_vals.get)

        # Execute rotation if target changed
        if target != current_holding:
            if current_holding is not None:
                portfolio.sell(current_holding, all_shares=True, date=date_str)

            dollars = portfolio.cash * 0.90
            result = portfolio.buy(target, dollars=dollars, date=date_str)
            if result:
                current_holding = target
                entry_price = result["exec_price"]

        last_rotation = i
