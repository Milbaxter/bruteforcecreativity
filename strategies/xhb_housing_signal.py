"""
XHB Housing Signal — SPDR Homebuilders ETF (XHB) direction as a housing
cycle signal. Housing leads the broader economy by 6-12 months.
Combined with Wikipedia "housing_bubble" attention as overheating filter.
"""
import pandas as pd
import numpy as np

STRATEGY = {
    "name": "XHB Housing Signal",
    "hypothesis": "Housing (XHB) is the economy's most rate-sensitive sector and the longest-lead indicator. When XHB rises, rate environment is favorable AND consumer confidence is high = growth. When XHB falls, rates are hurting or consumers are pulling back = safety.",
    "universe": ["XHB", "SOXX", "GDX", "SLV", "XLF"],
    "entry": "XHB 7d momentum positive + wiki housing bubble stable: buy SOXX/XLF. XHB negative: buy GDX/SLV.",
    "exit": "Rotate every 5 trading days",
    "position_size": "100% in best 5d momentum candidate per regime",
    "eccentricity": "Homebuilder stocks as a macro leading indicator — housing starts lead GDP by 2-3 quarters but XHB leads housing starts by 1-2 months. It's the leading indicator of a leading indicator.",
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
    if "XHB" not in prices or len(prices) < 4:
        return
    try:
        wiki = data_fetcher.get_wikipedia_pageviews("United_States_housing_bubble")
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
        sig = prices["XHB"]
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
