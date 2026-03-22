"""
Google Layoffs Sector Shift — Google Trends for "layoffs" as a labor market
stress signal. Rising layoff searches = rotate defensive. Falling = growth.

Combined with crypto fear/greed as secondary confirmation and momentum selection.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Google Layoffs Sector Shift",
    "hypothesis": "Google searches for 'layoffs' lead actual labor market data by 2-4 weeks. Rising searches signal consumer/corporate stress before official data confirms it. Defensive sectors outperform during stress.",
    "universe": ["SOXX", "GDX", "SLV", "XLP"],
    "entry": "Layoffs trend rising + crypto fear < 60: buy defensive (GDX/SLV/XLP). Layoffs falling + crypto fear > 30: buy growth (SOXX).",
    "exit": "Rotate every 5 trading days based on updated Google Trends signal",
    "position_size": "100% in best momentum candidate per regime",
    "eccentricity": "Using Google search behavior as a leading labor market indicator — retail investors googling 'layoffs' before the BLS reports the data.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Fetch Google Trends for "layoffs"
    try:
        trends = data_fetcher.get_google_trends(["layoffs"])
    except Exception:
        trends = None

    if trends is None or trends.empty:
        return

    if isinstance(trends, pd.DataFrame):
        if "layoffs" in trends.columns:
            trend_series = trends["layoffs"]
        else:
            trend_series = trends.iloc[:, 0]
    else:
        trend_series = trends

    trend_series.index = pd.to_datetime(trend_series.index)
    trend_series = trend_series.sort_index()

    # Get crypto fear/greed
    try:
        fear_greed = data_fetcher.get_crypto_fear_greed(days=400)
    except Exception:
        fear_greed = None

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

    if len(prices) < 2:
        return

    all_dates = set()
    for df in prices.values():
        for dt in df.index:
            all_dates.add(dt)
    trading_days = sorted(all_dates)

    if len(trading_days) < 30:
        return

    defensive_tickers = ["GDX", "SLV", "XLP"]
    growth_tickers = ["SOXX"]

    current_holding = None
    last_rotation_idx = -999
    rotation_interval = 5

    for i, day in enumerate(trading_days):
        if i < 20:
            continue
        if i - last_rotation_idx < rotation_interval:
            continue

        date_str = day.strftime("%Y-%m-%d") if hasattr(day, 'strftime') else str(day)[:10]

        # Get layoffs trend direction (weekly data — find latest before this date)
        trend_before = trend_series[trend_series.index <= day]
        if len(trend_before) < 5:
            continue

        current_trend = float(trend_before.iloc[-1])
        past_trend = float(trend_before.iloc[-4]) if len(trend_before) >= 4 else float(trend_before.iloc[0])

        if past_trend == 0:
            continue

        trend_change = (current_trend - past_trend) / max(past_trend, 1)

        # Get crypto fear/greed
        fg_val = 50  # default neutral
        if fear_greed is not None and not fear_greed.empty:
            fg_before = fear_greed[fear_greed.index <= day]
            if len(fg_before) > 0:
                fg_val = float(fg_before.iloc[-1])

        # Determine regime
        if trend_change > 0.15 and fg_val < 65:
            # Layoffs trending up — defensive
            candidates = [t for t in defensive_tickers if t in prices]
        elif trend_change < -0.10 and fg_val > 25:
            # Layoffs trending down — growth
            candidates = [t for t in growth_tickers if t in prices]
        else:
            # Mixed — pick best momentum across all
            candidates = [t for t in universe if t in prices]

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
