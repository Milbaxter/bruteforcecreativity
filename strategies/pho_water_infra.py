"""
PHO Water Infrastructure — Invesco Water Resources ETF (PHO) direction
as an infrastructure spending signal.

Water infrastructure stocks are ultra-defensive and government-funded.
When PHO rises, infrastructure spending is flowing = stable economy.
When PHO falls, even defensive infrastructure is hurting = broad stress.
Combined with Wikipedia "infrastructure" attention.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "PHO Water Infrastructure",
    "hypothesis": "Water infrastructure stocks (PHO) are the most boring, stable, government-backed sector. When even PHO is falling, the economy is in serious stress. PHO direction is a 'canary in the mine' for defensive sector health — if the safest stocks are selling off, nothing is safe.",
    "universe": ["PHO", "SOXX", "GDX", "SLV", "XLF"],
    "entry": "PHO 7d momentum positive: buy SOXX/XLF. PHO negative + wiki infra attention: buy GDX/SLV.",
    "exit": "Rotate every 5 trading days",
    "position_size": "100% in best 5d momentum candidate per regime",
    "eccentricity": "Water infrastructure as a macro signal — nobody watches PHO for sector rotation. But its movement reveals whether government spending and utility demand are intact.",
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

    if "PHO" not in prices or len(prices) < 4:
        return

    try:
        wiki = data_fetcher.get_wikipedia_pageviews("Infrastructure")
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

        pho = prices["PHO"]
        pb = pho[pho.index <= day]
        if len(pb) < 8:
            continue
        mom = (float(pb["Close"].iloc[-1]) - float(pb["Close"].iloc[-8])) / float(pb["Close"].iloc[-8])

        concern = False
        if wiki is not None:
            w = wiki[wiki.index <= day]
            if len(w) >= 20:
                r = float(w.iloc[-5:].mean())
                a = float(w.iloc[-20:].mean())
                if a > 0:
                    concern = r > a * 1.5

        if mom > 0.003:
            cands = [t for t in growth if t in prices]
        elif mom < -0.003 or concern:
            cands = [t for t in safety if t in prices]
        else:
            cands = [t for t in growth + safety if t in prices]

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
