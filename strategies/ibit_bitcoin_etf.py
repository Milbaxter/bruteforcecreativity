"""
IBIT Bitcoin ETF Signal — iShares Bitcoin Trust (IBIT) direction as an
institutional crypto adoption signal.

IBIT captures institutional BTC flows (not retail crypto speculation).
When IBIT trends up, institutional money is flowing into risk assets.
When IBIT trends down, institutions are pulling back from risk.
Combined with Wikipedia "cryptocurrency" attention as retail confirmation.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "IBIT Bitcoin ETF Signal",
    "hypothesis": "IBIT tracks institutional Bitcoin adoption. When IBIT rises, Wall Street is risk-on and rotating into speculative assets = bullish for growth. When IBIT falls, institutional risk appetite is declining = defensive mode. More institutional than BTC-USD itself.",
    "universe": ["IBIT", "SOXX", "GDX", "SLV", "XLF"],
    "entry": "IBIT 7d momentum positive + wiki crypto attention not panicking: buy SOXX/XLF. IBIT negative: buy GDX/SLV.",
    "exit": "Rotate every 5 trading days",
    "position_size": "100% in best 5d momentum candidate per regime",
    "eccentricity": "Using the Bitcoin ETF as a macro risk signal for traditional sectors — IBIT didn't exist 2 years ago. It's the newest barometer of institutional risk appetite.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    prices = {}
    for ticker in STRATEGY["universe"]:
        try:
            df = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            prices[ticker] = df
        except Exception:
            continue

    if "IBIT" not in prices or len(prices) < 4:
        return

    try:
        wiki_crypto = data_fetcher.get_wikipedia_pageviews("Cryptocurrency")
        if wiki_crypto is not None and not wiki_crypto.empty:
            wiki_crypto.index = pd.to_datetime(wiki_crypto.index)
            wiki_crypto = wiki_crypto.sort_index()
        else:
            wiki_crypto = None
    except Exception:
        wiki_crypto = None

    all_dates = set()
    for df in prices.values():
        for dt in df.index:
            all_dates.add(dt)
    trading_days = sorted(all_dates)

    if len(trading_days) < 20:
        return

    growth_tickers = ["SOXX", "XLF"]
    safety_tickers = ["GDX", "SLV"]

    current_holding = None
    last_rotation_idx = -999
    rotation_interval = 5
    lookback = 7

    for i, day in enumerate(trading_days):
        if i < lookback + 5:
            continue
        if i - last_rotation_idx < rotation_interval:
            continue

        date_str = day.strftime("%Y-%m-%d") if hasattr(day, 'strftime') else str(day)[:10]

        ibit = prices["IBIT"]
        ibit_before = ibit[ibit.index <= day]
        if len(ibit_before) < lookback + 1:
            continue

        ibit_now = float(ibit_before["Close"].iloc[-1])
        ibit_past = float(ibit_before["Close"].iloc[-lookback - 1])
        if ibit_past == 0:
            continue

        ibit_mom = (ibit_now - ibit_past) / ibit_past

        crypto_panic = False
        if wiki_crypto is not None:
            wc = wiki_crypto[wiki_crypto.index <= day]
            if len(wc) >= 20:
                recent = float(wc.iloc[-5:].mean())
                avg = float(wc.iloc[-20:].mean())
                if avg > 0:
                    crypto_panic = recent > avg * 1.5

        if ibit_mom > 0.01 and not crypto_panic:
            candidates = [t for t in growth_tickers if t in prices]
        elif ibit_mom < -0.01 or crypto_panic:
            candidates = [t for t in safety_tickers if t in prices]
        else:
            candidates = [t for t in growth_tickers + safety_tickers if t in prices]

        if not candidates:
            continue

        best_ticker = None
        best_mom = -999
        for ticker in candidates:
            df = prices[ticker]
            df_before = df[df.index <= day]
            if len(df_before) < 6:
                continue
            c_now = float(df_before["Close"].iloc[-1])
            c_5d = float(df_before["Close"].iloc[-6])
            if c_5d > 0:
                mom = (c_now - c_5d) / c_5d
                if mom > best_mom:
                    best_mom = mom
                    best_ticker = ticker

        if best_ticker is None:
            continue

        if best_ticker != current_holding:
            if current_holding and current_holding in portfolio.positions:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
            portfolio.buy(best_ticker, dollars=portfolio.cash * 0.98, date=date_str)
            current_holding = best_ticker
            last_rotation_idx = i

    if current_holding and current_holding in portfolio.positions:
        end_str = trading_days[-1].strftime("%Y-%m-%d") if hasattr(trading_days[-1], 'strftime') else str(trading_days[-1])[:10]
        portfolio.sell(current_holding, all_shares=True, date=end_str)
