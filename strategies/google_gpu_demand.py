"""
Google GPU Demand — Google Trends for "GPU" as a real-time semiconductor
demand proxy. Rising GPU search interest = growing compute demand = SOXX.
Falling search interest + SOXX weakness = hype cooling = rotate to safety.

Combined with crypto fear/greed as risk filter.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Google GPU Demand",
    "hypothesis": "Google searches for 'GPU' capture real-time demand signals for semiconductor/AI compute. When GPU interest rises, enterprises and consumers are actively seeking chips = bullish SOXX. When interest wanes, the hype cycle is cooling.",
    "universe": ["SOXX", "GDX", "SLV", "XLF"],
    "entry": "GPU trend rising (4-week): buy SOXX. GPU trend falling: buy GDX/SLV/XLF best momentum.",
    "exit": "Rotate every 5 trading days based on updated Google Trends",
    "position_size": "100% in best momentum candidate per regime",
    "eccentricity": "Google search behavior as a demand signal for the semiconductor supply chain — retail investors googling 'GPU' before analysts publish earnings estimates.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Fetch Google Trends for GPU
    try:
        trends = data_fetcher.get_google_trends(["GPU"])
    except Exception:
        trends = None

    if trends is None or trends.empty:
        return

    if isinstance(trends, pd.DataFrame):
        if "GPU" in trends.columns:
            trend_series = trends["GPU"]
        else:
            trend_series = trends.iloc[:, 0]
    else:
        trend_series = trends

    trend_series.index = pd.to_datetime(trend_series.index)
    trend_series = trend_series.sort_index()

    if len(trend_series) < 8:
        return

    # Crypto fear/greed
    try:
        fear_greed = data_fetcher.get_crypto_fear_greed(days=400)
    except Exception:
        fear_greed = None

    # Get prices
    prices = {}
    for ticker in STRATEGY["universe"]:
        try:
            df = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            prices[ticker] = df
        except Exception:
            continue

    if len(prices) < 3:
        return

    all_dates = set()
    for df in prices.values():
        for dt in df.index:
            all_dates.add(dt)
    trading_days = sorted(all_dates)

    if len(trading_days) < 20:
        return

    growth_tickers = ["SOXX"]
    safety_tickers = ["GDX", "SLV", "XLF"]

    current_holding = None
    last_rotation_idx = -999
    rotation_interval = 5

    for i, day in enumerate(trading_days):
        if i < 15:
            continue
        if i - last_rotation_idx < rotation_interval:
            continue

        date_str = day.strftime("%Y-%m-%d") if hasattr(day, 'strftime') else str(day)[:10]

        # Crypto fear filter
        fg_val = 50
        if fear_greed is not None and not fear_greed.empty:
            fg_before = fear_greed[fear_greed.index <= day]
            if len(fg_before) > 0:
                fg_val = float(fg_before.iloc[-1])
        if fg_val < 15:
            continue

        # Google Trends GPU direction (weekly data)
        trend_before = trend_series[trend_series.index <= day]
        if len(trend_before) < 5:
            continue

        current_val = float(trend_before.iloc[-1])
        past_val = float(trend_before.iloc[-4]) if len(trend_before) >= 4 else float(trend_before.iloc[0])

        if past_val == 0:
            trend_change = 0
        else:
            trend_change = (current_val - past_val) / max(past_val, 1)

        # Also check if SOXX is above its 10d MA
        soxx_bullish = True
        if "SOXX" in prices:
            soxx_df = prices["SOXX"]
            soxx_before = soxx_df[soxx_df.index <= day]
            if len(soxx_before) >= 10:
                soxx_price = float(soxx_before["Close"].iloc[-1])
                soxx_ma = float(soxx_before["Close"].iloc[-10:].mean())
                soxx_bullish = soxx_price > soxx_ma

        # Determine regime
        if trend_change > 0.05 and soxx_bullish:
            candidates = [t for t in growth_tickers if t in prices]
        elif trend_change < -0.05 or not soxx_bullish:
            candidates = [t for t in safety_tickers if t in prices]
        else:
            candidates = [t for t in STRATEGY["universe"] if t in prices]

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
