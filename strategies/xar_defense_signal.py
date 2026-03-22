"""
XAR Defense Signal — SPDR Aerospace & Defense ETF (XAR) direction as
a geopolitical spending signal.

Rising XAR = defense spending increasing = geopolitical tension = but
also government spending flowing = mixed signal.
Combined with Wikipedia "military_budget" attention and crypto fear.
When defense rises AND crypto fear is low = broad risk on.
When defense rises AND crypto fear is high = geopolitical risk = safety.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "XAR Defense Signal",
    "hypothesis": "Defense stock direction combined with crypto fear creates a 2x2 matrix: (1) Defense up + low fear = fiscal expansion = growth, (2) Defense up + high fear = geopolitical tension = safety, (3) Defense down + low fear = peace dividend = growth, (4) Defense down + high fear = broad sell-off = safety.",
    "universe": ["XAR", "SOXX", "GDX", "SLV", "XLF"],
    "entry": "XAR direction + crypto fear/greed create a 2x2 regime matrix selecting growth vs safety",
    "exit": "Rotate every 5 trading days",
    "position_size": "100% in best 5d momentum candidate per regime",
    "eccentricity": "Defense spending as a macro signal — combines geopolitical risk (usually bullish for gold) with fiscal expansion (usually bullish for growth). The crypto fear overlay disambiguates which effect dominates.",
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

    if "XAR" not in prices or len(prices) < 4:
        return

    try:
        fear_greed = data_fetcher.get_crypto_fear_greed(days=400)
    except Exception:
        fear_greed = None

    try:
        wiki = data_fetcher.get_wikipedia_pageviews("Military_budget_of_the_United_States")
        if wiki is not None and not wiki.empty:
            wiki.index = pd.to_datetime(wiki.index)
            wiki = wiki.sort_index()
        else:
            wiki = None
    except Exception:
        wiki = None

    all_dates = set()
    for df in prices.values():
        for dt in df.index:
            all_dates.add(dt)
    trading_days = sorted(all_dates)
    if len(trading_days) < 20:
        return

    growth = ["SOXX", "XLF"]
    safety = ["GDX", "SLV"]
    current_holding = None
    last_rot = -999

    for i, day in enumerate(trading_days):
        if i < 12 or i - last_rot < 5:
            continue
        date_str = day.strftime("%Y-%m-%d") if hasattr(day, 'strftime') else str(day)[:10]

        xar = prices["XAR"]
        xb = xar[xar.index <= day]
        if len(xb) < 8:
            continue
        xar_mom = (float(xb["Close"].iloc[-1]) - float(xb["Close"].iloc[-8])) / float(xb["Close"].iloc[-8])

        fg_val = 50
        if fear_greed is not None and not fear_greed.empty:
            fg_before = fear_greed[fear_greed.index <= day]
            if len(fg_before) > 0:
                fg_val = float(fg_before.iloc[-1])

        # 2x2 matrix
        if xar_mom > 0 and fg_val > 40:
            # Defense up + low fear = fiscal expansion = growth
            cands = [t for t in growth if t in prices]
        elif xar_mom > 0 and fg_val <= 40:
            # Defense up + high fear = geopolitical tension = safety
            cands = [t for t in safety if t in prices]
        elif xar_mom <= 0 and fg_val > 40:
            # Defense down + low fear = peace/stable = growth
            cands = [t for t in growth if t in prices]
        else:
            # Defense down + high fear = broad risk off = safety
            cands = [t for t in safety if t in prices]

        if not cands:
            continue
        best = None
        bm = -999
        for t in cands:
            d = prices[t]
            db = d[d.index <= day]
            if len(db) < 6:
                continue
            m = (float(db["Close"].iloc[-1]) - float(db["Close"].iloc[-6])) / float(db["Close"].iloc[-6])
            if m > bm:
                bm = m
                best = t
        if best and best != current_holding:
            if current_holding and current_holding in portfolio.positions:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
            portfolio.buy(best, dollars=portfolio.cash * 0.98, date=date_str)
            current_holding = best
            last_rot = i

    if current_holding and current_holding in portfolio.positions:
        e = trading_days[-1].strftime("%Y-%m-%d") if hasattr(trading_days[-1], 'strftime') else str(trading_days[-1])[:10]
        portfolio.sell(current_holding, all_shares=True, date=e)
