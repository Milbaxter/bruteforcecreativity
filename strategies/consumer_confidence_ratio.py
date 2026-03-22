"""
Consumer Confidence Ratio — XLY/XLP (discretionary vs staples) ratio direction
as a real-time consumer confidence proxy for sector rotation.

Rising XLY/XLP = consumers confident, spending on discretionary = growth mode.
Falling XLY/XLP = consumers defensive, spending on staples = safety mode.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Consumer Confidence Ratio",
    "hypothesis": "The XLY/XLP ratio is the market's real-time vote on consumer confidence, updated daily rather than monthly like survey data. When consumers shift from discretionary to staples spending, it signals economic slowdown before GDP confirms it.",
    "universe": ["XLY", "XLP", "SOXX", "GDX", "SLV", "XLF"],
    "entry": "XLY/XLP ratio rising (10d trend): buy SOXX or XLF (best 5d momentum). Ratio falling: buy GDX or SLV (best 5d momentum).",
    "exit": "Rotate every 5 trading days based on updated ratio direction",
    "position_size": "100% in single best candidate per regime",
    "eccentricity": "Using the equity market's own consumer spending signal as a macro indicator — the XLY/XLP ratio is overlooked by most retail traders who watch VIX instead.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Need XLY and XLP to compute ratio, plus trading candidates
    all_tickers = STRATEGY["universe"]
    prices = {}
    for ticker in all_tickers:
        try:
            df = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            prices[ticker] = df
        except Exception:
            continue

    if "XLY" not in prices or "XLP" not in prices:
        return

    # Compute XLY/XLP ratio on common dates
    xly = prices["XLY"]
    xlp = prices["XLP"]
    common = xly.index.intersection(xlp.index)
    if len(common) < 30:
        return

    ratio = xly.loc[common, "Close"] / xlp.loc[common, "Close"]

    # Get crypto fear/greed as secondary filter
    try:
        fear_greed = data_fetcher.get_crypto_fear_greed(days=400)
    except Exception:
        fear_greed = None

    # Trading days from all price data
    all_dates = set()
    for df in prices.values():
        for dt in df.index:
            all_dates.add(dt)
    trading_days = sorted(all_dates)

    growth_tickers = ["SOXX", "XLF"]
    safety_tickers = ["GDX", "SLV"]

    current_holding = None
    last_rotation_idx = -999
    rotation_interval = 5
    lookback = 10

    for i, day in enumerate(trading_days):
        if i < lookback + 5:
            continue
        if i - last_rotation_idx < rotation_interval:
            continue

        date_str = day.strftime("%Y-%m-%d") if hasattr(day, 'strftime') else str(day)[:10]

        # Get ratio direction
        ratio_before = ratio[ratio.index <= day]
        if len(ratio_before) < lookback + 1:
            continue

        current_ratio = float(ratio_before.iloc[-1])
        past_ratio = float(ratio_before.iloc[-lookback - 1])

        if past_ratio == 0:
            continue

        ratio_change = (current_ratio - past_ratio) / past_ratio

        # Crypto fear/greed filter
        fg_val = 50
        if fear_greed is not None and not fear_greed.empty:
            fg_before = fear_greed[fear_greed.index <= day]
            if len(fg_before) > 0:
                fg_val = float(fg_before.iloc[-1])

        if fg_val < 15:
            continue  # extreme panic, sit out

        # Determine regime
        if ratio_change > 0.005:  # consumer confidence rising
            candidates = [t for t in growth_tickers if t in prices]
        elif ratio_change < -0.005:  # consumer confidence falling
            candidates = [t for t in safety_tickers if t in prices]
        else:
            candidates = [t for t in STRATEGY["universe"] if t in prices and t not in ["XLY", "XLP"]]

        if not candidates:
            continue

        # Pick best 5d momentum
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
