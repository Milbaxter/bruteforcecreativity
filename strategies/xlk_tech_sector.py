"""
XLK Tech Sector Signal — Technology Select Sector (XLK) direction as
the broadest tech spending signal. Different from SOXX (which is in the
trading universe). XLK includes Apple, Microsoft, NVDA = mega-cap tech.
Combined with Wikipedia "information_technology" attention.
"""
import pandas as pd
import numpy as np

STRATEGY = {
    "name": "XLK Tech Sector Signal",
    "hypothesis": "XLK is the broadest tech sector signal including mega-caps. When XLK rises, the entire tech ecosystem is healthy = growth assets benefit. When XLK falls, tech leadership is failing = safety mode.",
    "universe": ["XLK", "SOXX", "GDX", "SLV", "XLF"],
    "entry": "XLK 7d momentum positive: buy SOXX/XLF. XLK negative: buy GDX/SLV.",
    "exit": "Rotate every 5 trading days",
    "position_size": "100% in best 5d momentum candidate per regime",
    "eccentricity": "Using XLK (not traded) to signal SOXX trades — the broader tech basket smooths out semiconductor-specific noise.",
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
    if "XLK" not in prices or len(prices) < 4:
        return
    try:
        wiki = data_fetcher.get_wikipedia_pageviews("Information_technology")
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
        sig = prices["XLK"]
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
        if mom > 0.005 and not concern:
            cands = [t for t in growth if t in prices]
        elif mom < -0.005 or concern:
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
