"""
Mortgage Rate Regime — use FRED 30Y mortgage rate direction to determine
whether housing/growth or commodity/safety assets should lead.

Falling mortgage rates = housing/rate-sensitive sectors rally.
Rising mortgage rates = inflation pressure = commodities benefit.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Mortgage Rate Regime",
    "hypothesis": "30Y mortgage rate direction captures the rate cycle that drives sector rotation. Falling rates boost housing, REITs, and growth. Rising rates signal inflation and boost commodities. Weekly frequency creates a persistent regime signal.",
    "universe": ["XLRE", "XHB", "GDX", "SLV", "SOXX"],
    "entry": "Rates falling: buy best momentum among XLRE/XHB/SOXX. Rates rising: buy best momentum among GDX/SLV.",
    "exit": "Rotate every 5 trading days based on updated signal",
    "position_size": "100% in single best candidate per regime",
    "eccentricity": "Mortgage rate as a rotation timer — most quants watch treasury yields but ignore mortgage spreads. The housing wealth effect creates a delayed transmission mechanism that small traders can exploit.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Fetch 30Y mortgage rate from FRED
    try:
        mortgage = data_fetcher.get_fred_series("MORTGAGE30US")
    except Exception:
        mortgage = None

    if mortgage is None or (hasattr(mortgage, 'empty') and mortgage.empty):
        # Fallback: use 10Y yield as proxy
        try:
            mortgage = data_fetcher.get_fred_series("DGS10")
        except Exception:
            return

    if mortgage is None or (hasattr(mortgage, 'empty') and mortgage.empty):
        return

    if isinstance(mortgage, pd.DataFrame):
        mortgage = mortgage.iloc[:, 0]
    mortgage.index = pd.to_datetime(mortgage.index)
    mortgage = mortgage.sort_index().dropna()

    # Get prices
    universe = STRATEGY["universe"]
    prices = {}
    for ticker in universe:
        try:
            df = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            prices[ticker] = df
        except Exception:
            continue

    if len(prices) < 3:
        return

    # Get crypto fear/greed as risk filter
    try:
        fear_greed = data_fetcher.get_crypto_fear_greed(days=400)
    except Exception:
        fear_greed = None

    all_dates = set()
    for df in prices.values():
        for dt in df.index:
            all_dates.add(dt)
    trading_days = sorted(all_dates)

    if len(trading_days) < 30:
        return

    rate_falling_tickers = ["XLRE", "XHB", "SOXX"]
    rate_rising_tickers = ["GDX", "SLV"]

    current_holding = None
    last_rotation_idx = -999
    rotation_interval = 5

    for i, day in enumerate(trading_days):
        if i < 20:
            continue
        if i - last_rotation_idx < rotation_interval:
            continue

        date_str = day.strftime("%Y-%m-%d") if hasattr(day, 'strftime') else str(day)[:10]

        # Check crypto fear/greed risk filter
        if fear_greed is not None and not fear_greed.empty:
            fg_before = fear_greed[fear_greed.index <= day]
            if len(fg_before) > 0:
                fg_val = float(fg_before.iloc[-1])
                if fg_val < 15:
                    continue  # extreme fear, stay out

        # Get mortgage rate direction
        mort_before = mortgage[mortgage.index <= day]
        if len(mort_before) < 6:
            continue

        current_rate = float(mort_before.iloc[-1])
        past_rate = float(mort_before.iloc[-5]) if len(mort_before) >= 5 else float(mort_before.iloc[0])

        if past_rate == 0:
            continue

        rate_change = (current_rate - past_rate) / past_rate

        # Determine regime
        if rate_change < -0.005:  # rates falling
            candidates = [t for t in rate_falling_tickers if t in prices]
        elif rate_change > 0.005:  # rates rising
            candidates = [t for t in rate_rising_tickers if t in prices]
        else:
            # Flat rates — use all candidates, pick best momentum
            candidates = [t for t in universe if t in prices]

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

    # Close at end
    if current_holding and current_holding in portfolio.positions:
        end_str = trading_days[-1].strftime("%Y-%m-%d") if hasattr(trading_days[-1], 'strftime') else str(trading_days[-1])[:10]
        portfolio.sell(current_holding, all_shares=True, date=end_str)
