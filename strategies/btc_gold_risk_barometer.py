"""
BTC Gold Risk Barometer — BTC-USD/GLD ratio direction as a cross-domain
risk appetite signal. BTC outperforming gold = risk on. Gold outperforming
BTC = risk off.

Combined with Wikipedia "Bitcoin" attention as confirmation.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "BTC Gold Risk Barometer",
    "hypothesis": "The BTC/GLD ratio captures the tug-of-war between risk appetite (crypto) and fear (gold). When BTC leads gold, the market is risk-on and growth assets outperform. When gold leads BTC, defensive posture wins. Wikipedia Bitcoin attention confirms retail engagement.",
    "universe": ["BTC-USD", "GLD", "SOXX", "GDX", "SLV", "XLF"],
    "entry": "BTC/GLD ratio rising + Bitcoin wiki attention stable/rising: buy SOXX/XLF. Ratio falling: buy GDX/SLV.",
    "exit": "Rotate every 5 trading days",
    "position_size": "100% in best momentum candidate per regime",
    "eccentricity": "Using the BTC/gold ratio as a macro risk gauge — an asset class that didn't exist 15 years ago now reveals risk sentiment better than VIX for retail-scale capital.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Get BTC and GLD prices
    prices = {}
    for ticker in STRATEGY["universe"]:
        try:
            df = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            prices[ticker] = df
        except Exception:
            continue

    if "BTC-USD" not in prices or "GLD" not in prices:
        return
    if len(prices) < 4:
        return

    # Compute BTC/GLD ratio
    btc = prices["BTC-USD"]
    gld = prices["GLD"]
    common = btc.index.intersection(gld.index)
    if len(common) < 30:
        return

    ratio = btc.loc[common, "Close"] / gld.loc[common, "Close"]

    # Wikipedia Bitcoin attention
    try:
        wiki_btc = data_fetcher.get_wikipedia_pageviews("Bitcoin")
        if wiki_btc is not None and not wiki_btc.empty:
            wiki_btc.index = pd.to_datetime(wiki_btc.index)
            wiki_btc = wiki_btc.sort_index()
        else:
            wiki_btc = None
    except Exception:
        wiki_btc = None

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

        # BTC/GLD ratio direction
        ratio_before = ratio[ratio.index <= day]
        if len(ratio_before) < lookback + 1:
            continue

        current_r = float(ratio_before.iloc[-1])
        past_r = float(ratio_before.iloc[-lookback - 1])
        if past_r == 0:
            continue

        ratio_change = (current_r - past_r) / past_r

        # Wikipedia Bitcoin attention as confirmation
        wiki_rising = True  # default assume neutral
        if wiki_btc is not None:
            wb = wiki_btc[wiki_btc.index <= day]
            if len(wb) >= 10:
                recent_avg = float(wb.iloc[-5:].mean())
                past_avg = float(wb.iloc[-10:-5].mean())
                if past_avg > 0:
                    wiki_rising = recent_avg >= past_avg * 0.8  # not falling sharply

        # Determine regime
        if ratio_change > 0.02 and wiki_rising:
            # BTC outperforming gold = risk on
            candidates = [t for t in growth_tickers if t in prices]
        elif ratio_change < -0.02:
            # Gold outperforming BTC = risk off
            candidates = [t for t in safety_tickers if t in prices]
        else:
            # Neutral
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
