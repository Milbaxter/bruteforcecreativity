"""
Biotech Silver Barbell
Momentum rotation across three high-beta, uncorrelated assets:
XBI (biotech), SLV (silver), IWM (small caps).
Each driven by different factors: FDA/M&A, precious metals, domestic growth.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Biotech Silver Barbell",
    "hypothesis": "XBI (biotech catalysts), SLV (precious metals trend), and IWM (small cap cycle) have low correlation but high individual volatility. Momentum rotation captures whichever high-beta asset is trending, delivering outsized returns vs broad market.",
    "universe": ["XBI", "SLV", "IWM"],
    "entry": "Buy the asset with strongest 7-day momentum. Rotate every 3 trading days.",
    "exit": "Rotate to new leader every 3 days, -4% stop loss per position",
    "position_size": "90% of capital in selected ETF",
    "eccentricity": "Barbell portfolio of biotech, silver, and small caps — no institutional fund would rotate between these three on a 3-day cycle. High volatility creates more rotation alpha.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    tickers = ["XBI", "SLV", "IWM"]

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
