"""
XRT Retail Direction — SPDR Retail ETF (XRT) direction as a consumer
spending signal for sector rotation.

Rising XRT = consumer spending healthy = economy expanding = growth.
Falling XRT = consumers pulling back = defensive mode.
Combined with Wikipedia "inflation" attention as price pressure gauge.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "XRT Retail Direction",
    "hypothesis": "Retail spending (XRT) is the consumer's real-time vote on the economy. When retail stocks rise, consumers are confident and spending freely = growth assets benefit. When retail stocks fall, spending is contracting = safety wins. More timely than monthly retail sales data.",
    "universe": ["XRT", "SOXX", "GDX", "SLV", "XLF"],
    "entry": "XRT 7d momentum positive: buy SOXX/XLF. XRT negative + inflation wiki rising: buy GDX/SLV.",
    "exit": "Rotate every 5 trading days",
    "position_size": "100% in best 5d momentum candidate per regime",
    "eccentricity": "Using retail stocks as a consumer confidence barometer — XRT captures Main Street reality while analysts debate GDP estimates.",
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

    if "XRT" not in prices or len(prices) < 4:
        return

    try:
        wiki_inf = data_fetcher.get_wikipedia_pageviews("Inflation")
        if wiki_inf is not None and not wiki_inf.empty:
            wiki_inf.index = pd.to_datetime(wiki_inf.index)
            wiki_inf = wiki_inf.sort_index()
        else:
            wiki_inf = None
    except Exception:
        wiki_inf = None

    all_dates = set()
    for df in prices.values():
        for dt in df.index:
            all_dates.add(dt)
    trading_days = sorted(all_dates)

    if len(trading_days) < 20:
        return

    growth_tickers = ["SOXX", "XLF"]
    safety_tickers = ["GDX", "SLV"]

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

        xrt = prices["XRT"]
        xrt_before = xrt[xrt.index <= day]
        if len(xrt_before) < lookback + 1:
            continue

        xrt_now = float(xrt_before["Close"].iloc[-1])
        xrt_past = float(xrt_before["Close"].iloc[-lookback - 1])
        if xrt_past == 0:
            continue

        xrt_mom = (xrt_now - xrt_past) / xrt_past

        inflation_concern = False
        if wiki_inf is not None:
            wi = wiki_inf[wiki_inf.index <= day]
            if len(wi) >= 20:
                recent = float(wi.iloc[-5:].mean())
                avg = float(wi.iloc[-20:].mean())
                if avg > 0:
                    inflation_concern = recent > avg * 1.3

        if xrt_mom > 0.003:
            candidates = [t for t in growth_tickers if t in prices]
        elif xrt_mom < -0.003 or inflation_concern:
            candidates = [t for t in safety_tickers if t in prices]
        else:
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
