"""
XOP Energy Demand — SPDR Oil & Gas Exploration (XOP) direction as an
energy demand signal for sector rotation.

When XOP rises, energy demand is strong = economic expansion = growth.
When XOP falls, energy demand is weakening = contraction risk = safety.
Combined with Wikipedia "oil_price" attention as supply shock filter.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "XOP Energy Demand",
    "hypothesis": "Oil & gas exploration stocks (XOP) are a real-time proxy for global energy demand. Rising XOP = strong industrial activity and transportation demand = growth cycle. Falling XOP = demand destruction or oversupply = deflationary risk = safety assets win.",
    "universe": ["XOP", "SOXX", "GDX", "SLV", "XLF"],
    "entry": "XOP 7d momentum positive: buy SOXX/XLF. XOP negative + oil wiki attention: buy GDX/SLV.",
    "exit": "Rotate every 5 trading days",
    "position_size": "100% in best 5d momentum candidate per regime",
    "eccentricity": "Oil exploration stocks as a macro demand indicator — captures both the energy cycle and the capex cycle simultaneously. Most traders look at crude oil price; XOP reveals the corporate response.",
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

    if "XOP" not in prices or len(prices) < 4:
        return

    try:
        wiki_oil = data_fetcher.get_wikipedia_pageviews("Price_of_oil")
        if wiki_oil is not None and not wiki_oil.empty:
            wiki_oil.index = pd.to_datetime(wiki_oil.index)
            wiki_oil = wiki_oil.sort_index()
        else:
            wiki_oil = None
    except Exception:
        wiki_oil = None

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
    last_rotation_idx = -999
    rotation_interval = 5
    lookback = 7

    for i, day in enumerate(trading_days):
        if i < lookback + 5:
            continue
        if i - last_rotation_idx < rotation_interval:
            continue

        date_str = day.strftime("%Y-%m-%d") if hasattr(day, 'strftime') else str(day)[:10]

        xop = prices["XOP"]
        xop_before = xop[xop.index <= day]
        if len(xop_before) < lookback + 1:
            continue

        xop_now = float(xop_before["Close"].iloc[-1])
        xop_past = float(xop_before["Close"].iloc[-lookback - 1])
        if xop_past == 0:
            continue

        xop_mom = (xop_now - xop_past) / xop_past

        oil_concern = False
        if wiki_oil is not None:
            wo = wiki_oil[wiki_oil.index <= day]
            if len(wo) >= 20:
                recent = float(wo.iloc[-5:].mean())
                avg = float(wo.iloc[-20:].mean())
                if avg > 0:
                    oil_concern = recent > avg * 1.4

        if xop_mom > 0.005:
            candidates = [t for t in growth if t in prices]
        elif xop_mom < -0.005 or oil_concern:
            candidates = [t for t in safety if t in prices]
        else:
            candidates = [t for t in growth + safety if t in prices]

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
