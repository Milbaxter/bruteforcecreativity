"""
Crypto-Equity Catch-Up
When BTC surges but crypto stocks lag, buy the stocks for the catch-up.
Combines: BTC momentum divergence + equity underperformance + volume confirmation.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Crypto Equity Catchup",
    "hypothesis": "When BTC-USD rallies >5% in 5 days but crypto-adjacent equities "
                  "(COIN, MARA, MSTR) lag by >3%, the equities catch up within 3-5 days. "
                  "This happens because crypto trades 24/7 while equities are on exchange hours — "
                  "the equity market takes time to digest crypto moves. Add volume filter: "
                  "only enter if equity volume is above average (institutions starting to notice).",
    "universe": ["COIN", "MARA", "MSTR", "BTC-USD"],
    "entry": "Buy when BTC 5-day return > 5% AND equity 5-day return < BTC 5-day return - 3% "
             "AND equity volume > 20-day average volume",
    "exit": "Sell after 5 days, +8% take profit, or -4% stop loss",
    "position_size": "30% of capital per position, max 2 concurrent",
    "eccentricity": "Cross-market arbitrage between 24/7 crypto and exchange-hours equities. "
                    "No traditional fund would systematically trade this BTC-to-equity lag because "
                    "it requires monitoring both crypto and equity markets simultaneously.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    equity_tickers = ["COIN", "MARA", "MSTR"]
    btc_ticker = "BTC-USD"

    # Fetch price data
    price_data = {}
    for ticker in equity_tickers:
        df = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if not df.empty:
            price_data[ticker] = df

    # Fetch BTC
    btc_df = data_fetcher.get_crypto_prices([btc_ticker], start=start_date, end=end_date)
    if isinstance(btc_df.columns, pd.MultiIndex):
        btc_df.columns = btc_df.columns.get_level_values(0)
    if btc_df.empty:
        return

    btc_close = btc_df["Close"]

    if not price_data:
        return

    # Get trading days from equity
    ref_ticker = next(iter(price_data))
    trading_days = price_data[ref_ticker].index.tolist()

    open_positions = {}  # ticker -> {entry_date, entry_price}
    MAX_POSITIONS = 2

    for i in range(10, len(trading_days)):
        date = trading_days[i]
        date_str = date.strftime("%Y-%m-%d")

        # Check exits
        tickers_to_close = []
        for ticker, pos in open_positions.items():
            if ticker not in price_data:
                continue
            current_price = float(price_data[ticker]["Close"].loc[:date].iloc[-1])
            entry_price = pos["entry_price"]
            days_held = (date - pos["entry_date"]).days
            pct_change = (current_price - entry_price) / entry_price

            if days_held >= 5 or pct_change >= 0.08 or pct_change <= -0.04:
                portfolio.sell(ticker, all_shares=True, date=date_str)
                tickers_to_close.append(ticker)

        for t in tickers_to_close:
            del open_positions[t]

        if len(open_positions) >= MAX_POSITIONS:
            continue

        # BTC 5-day return
        btc_before = btc_close.loc[:date]
        if len(btc_before) < 6:
            continue
        btc_now = float(btc_before.iloc[-1])
        btc_5d_ago = float(btc_before.iloc[-6])
        btc_5d_ret = (btc_now - btc_5d_ago) / btc_5d_ago

        # Only trigger when BTC is surging
        if btc_5d_ret < 0.05:
            continue

        # Score equity candidates by divergence
        candidates = []
        for ticker in equity_tickers:
            if ticker in open_positions:
                continue
            if ticker not in price_data:
                continue

            closes = price_data[ticker]["Close"].loc[:date]
            if len(closes) < 25:
                continue

            # Equity 5-day return
            eq_now = float(closes.iloc[-1])
            eq_5d_ago = float(closes.iloc[-6]) if len(closes) > 6 else float(closes.iloc[0])
            eq_5d_ret = (eq_now - eq_5d_ago) / eq_5d_ago

            # Divergence: BTC surging, equity lagging
            divergence = btc_5d_ret - eq_5d_ret
            if divergence < 0.03:
                continue  # Not enough lag

            # Volume confirmation: above 20-day average
            if "Volume" in price_data[ticker].columns:
                vol = price_data[ticker]["Volume"].loc[:date]
                if len(vol) >= 20:
                    vol_now = float(vol.iloc[-1])
                    vol_avg = float(vol.iloc[-20:].mean())
                    if vol_avg > 0 and vol_now < vol_avg:
                        continue  # Volume below average — institutions not engaged yet

            candidates.append((ticker, divergence))

        candidates.sort(key=lambda x: x[1], reverse=True)

        for ticker, div in candidates:
            if len(open_positions) >= MAX_POSITIONS:
                break

            dollars = portfolio.cash * 0.30
            if dollars < 100:
                break

            result = portfolio.buy(ticker, dollars=dollars, date=date_str)
            if result:
                open_positions[ticker] = {
                    "entry_date": date,
                    "entry_price": result["exec_price"],
                }
