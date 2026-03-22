"""
Wiki Geopolitics Gold — when Wikipedia attention for geopolitical conflict
articles spikes, buy gold as a safe haven trade.

Uses breadth of geopolitical attention (multiple articles) rather than
a single indicator.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Wiki Geopolitics Gold",
    "hypothesis": "Spikes in Wikipedia pageviews for geopolitical conflict articles signal rising geopolitical risk. Gold benefits as safe haven. Breadth across multiple articles reduces false signals from single-event noise.",
    "universe": ["GLD", "GDX", "SOXX", "XLF"],
    "entry": "Buy GLD/GDX when 2+ geopolitical wiki articles show >40% spike above 20d average. Buy SOXX/XLF when attention is low/normal.",
    "exit": "Rotate every 5 trading days based on updated attention signal",
    "position_size": "100% in best momentum candidate per regime",
    "eccentricity": "Using Wikipedia as a geopolitical risk barometer — institutional funds use Bloomberg terminal alerts, not Wikipedia pageviews. The crowd-sourced attention signal captures genuine public fear.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Geopolitical Wikipedia articles to track
    geo_articles = [
        "NATO",
        "International_sanctions",
        "Nuclear_weapon",
        "Trade_war",
        "War",
    ]

    # Fetch pageviews for each
    pageviews = {}
    for article in geo_articles:
        try:
            pv = data_fetcher.get_wikipedia_pageviews(article)
            if pv is not None and not pv.empty:
                pv.index = pd.to_datetime(pv.index)
                pageviews[article] = pv.sort_index()
        except Exception:
            continue

    if len(pageviews) < 2:
        return

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

    # Crypto fear/greed as secondary filter
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

    safety_tickers = ["GLD", "GDX"]
    growth_tickers = ["SOXX", "XLF"]

    current_holding = None
    last_rotation_idx = -999
    rotation_interval = 5
    lookback = 20
    spike_threshold = 0.40  # 40% above average

    for i, day in enumerate(trading_days):
        if i < lookback + 5:
            continue
        if i - last_rotation_idx < rotation_interval:
            continue

        date_str = day.strftime("%Y-%m-%d") if hasattr(day, 'strftime') else str(day)[:10]

        # Count how many geopolitical articles show attention spikes
        spike_count = 0
        for article, pv in pageviews.items():
            pv_before = pv[pv.index <= day]
            if len(pv_before) < lookback + 1:
                continue

            recent_avg = pv_before.iloc[-lookback:].mean()
            current_val = pv_before.iloc[-1]

            if recent_avg > 0 and current_val > recent_avg * (1 + spike_threshold):
                spike_count += 1

        # Determine regime based on breadth of geopolitical attention
        if spike_count >= 2:
            # Elevated geopolitical risk — safety assets
            candidates = [t for t in safety_tickers if t in prices]
        else:
            # Normal — growth assets
            candidates = [t for t in growth_tickers if t in prices]

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
