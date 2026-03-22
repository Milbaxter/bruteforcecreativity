"""
UNG Natural Gas Demand — United States Natural Gas Fund (UNG) direction
as a heating/cooling energy demand signal.
Rising UNG = energy demand spike (heating/cooling) = growth.
Combined with Wikipedia "natural_gas" attention.
"""
import pandas as pd
import numpy as np

STRATEGY = {
    "name": "UNG Natural Gas Demand",
    "hypothesis": "Natural gas demand (UNG) reflects heating/cooling energy needs plus industrial usage. Rising UNG = real energy demand = economic activity. Falling UNG = mild weather or demand destruction = safety. Natgas is less geopolitically distorted than crude oil.",
    "universe": ["UNG", "SOXX", "GDX", "SLV", "XLF"],
    "entry": "UNG 7d momentum positive: buy SOXX/XLF. UNG negative: buy GDX/SLV.",
    "exit": "Rotate every 5 trading days",
    "position_size": "100% in best 5d momentum candidate per regime",
    "eccentricity": "Natural gas as a macro signal — natgas captures real domestic energy demand without OPEC distortion. It's a purer demand signal than crude oil.",
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
    if "UNG" not in prices or len(prices) < 4:
        return
    try:
        wiki = data_fetcher.get_wikipedia_pageviews("Natural_gas")
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
        sig = prices["UNG"]
        sb = sig[sig.index <= day]
        if len(sb) < 8:
            continue
        mom = (float(sb["Close"].iloc[-1]) - float(sb["Close"].iloc[-8])) / float(sb["Close"].iloc[-8])
        concern = False
        if wiki is not None:
            w = wiki[wiki.index <= day]
            if len(w) >= 20:
                r, a = float(w.iloc[-5:].mean()), float(w.iloc[-20:].mean())
                if a > 0:
                    concern = r > a * 1.5
        if mom > 0.02 and not concern:
            cands = [t for t in growth if t in prices]
        elif mom < -0.02 or concern:
            cands = [t for t in safety if t in prices]
        else:
            cands = [t for t in growth + safety if t in prices]
        if not cands:
            continue
        best, bm = None, -999
        for t in cands:
            d = prices[t]
            db = d[d.index <= day]
            if len(db) < 6:
                continue
            m = (float(db["Close"].iloc[-1]) - float(db["Close"].iloc[-6])) / float(db["Close"].iloc[-6])
            if m > bm:
                bm, best = m, t
        if best and best != current_holding:
            if current_holding and current_holding in portfolio.positions:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
            portfolio.buy(best, dollars=portfolio.cash * 0.98, date=date_str)
            current_holding, last_rot = best, i

    if current_holding and current_holding in portfolio.positions:
        e = trading_days[-1].strftime("%Y-%m-%d") if hasattr(trading_days[-1], 'strftime') else str(trading_days[-1])[:10]
        portfolio.sell(current_holding, all_shares=True, date=e)
