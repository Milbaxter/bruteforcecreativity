"""
VNQ REIT Direction — Vanguard REIT ETF (VNQ) direction as an interest
rate sensitivity signal. REITs are the most rate-sensitive sector.

When VNQ rises, rate environment is favorable = growth.
When VNQ falls, rates are hurting = safety mode.
Combined with Wikipedia "interest_rate" attention.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "VNQ REIT Direction",
    "hypothesis": "REITs (VNQ) are the equity market's most rate-sensitive sector. When VNQ trends up, the rate environment is favorable for all growth assets. When VNQ trends down, rates are tightening or rising = headwind for growth = safety assets win. VNQ is a cleaner rate signal than watching bond yields directly.",
    "universe": ["VNQ", "SOXX", "GDX", "SLV", "XLF"],
    "entry": "VNQ 7d momentum positive + wiki interest rate stable: buy SOXX/XLF. VNQ negative: buy GDX/SLV.",
    "exit": "Rotate every 5 trading days",
    "position_size": "100% in best 5d momentum candidate per regime",
    "eccentricity": "Using REITs as a rate signal for sector rotation — most traders watch treasuries, but VNQ incorporates both rate sensitivity AND growth expectations in one signal.",
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

    if "VNQ" not in prices or len(prices) < 4:
        return

    try:
        wiki = data_fetcher.get_wikipedia_pageviews("Interest_rate")
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

        vnq = prices["VNQ"]
        vb = vnq[vnq.index <= day]
        if len(vb) < 8:
            continue
        mom = (float(vb["Close"].iloc[-1]) - float(vb["Close"].iloc[-8])) / float(vb["Close"].iloc[-8])

        rate_concern = False
        if wiki is not None:
            w = wiki[wiki.index <= day]
            if len(w) >= 20:
                r = float(w.iloc[-5:].mean())
                a = float(w.iloc[-20:].mean())
                if a > 0:
                    rate_concern = r > a * 1.4

        if mom > 0.005 and not rate_concern:
            cands = [t for t in growth if t in prices]
        elif mom < -0.005 or rate_concern:
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
