"""
Congress Sector Boost — congressional trades boost relative strength for specific sectors.

When congress members are actively BUYING in a sector (tech, financials, energy),
add a bonus to that sector's relative strength score. Congressional trading is a
known informational edge — they often know about upcoming policy changes.

Map congressional trades to sector ETFs:
- Tech tickers (AAPL, MSFT, NVDA, GOOG, META) → boost SOXX
- Finance tickers (JPM, GS, BAC) → boost XLF
- Energy tickers (XOM, CVX) → boost SLV (commodity proxy)
- Mining/materials → boost GDX

Base strategy: SPY relative strength across SLV/XLF/SOXX/GDX
Congressional activity adds +2% bonus to relative strength score.
"""

import pandas as pd
import numpy as np

ASSETS = ["SLV", "XLF", "SOXX", "GDX"]

TICKER_TO_SECTOR = {
    "AAPL": "SOXX", "MSFT": "SOXX", "NVDA": "SOXX", "GOOG": "SOXX",
    "GOOGL": "SOXX", "META": "SOXX", "AVGO": "SOXX", "AMD": "SOXX",
    "JPM": "XLF", "GS": "XLF", "BAC": "XLF", "MS": "XLF", "C": "XLF",
    "XOM": "SLV", "CVX": "SLV", "COP": "SLV", "SLB": "SLV",
    "NEM": "GDX", "GOLD": "GDX", "AEM": "GDX",
}

STRATEGY = {
    "name": "Congress Sector Boost",
    "hypothesis": "Congressional buying activity boosts relative strength for the corresponding sector ETF. Informational edge from policy knowledge.",
    "universe": ASSETS + ["SPY"],
    "entry": "SPY relative strength + congressional trade bonus for actively-bought sectors.",
    "exit": "Rotate every 3 days or -3% stop",
    "position_size": "90% of capital",
    "eccentricity": "Congressional trading data as informational boost for sector relative strength. Policy knowledge signals sector allocation.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Fetch congressional trades
    try:
        congress = data_fetcher.get_congressional_trades(days_back=30)
    except Exception:
        congress = pd.DataFrame()

    prices = {}
    for a in ASSETS + ["SPY"]:
        df = data_fetcher.get_prices(a, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            prices[a] = s

    if len(prices) < 5:
        return

    common = None
    for s in prices.values():
        common = s.index if common is None else common.intersection(s.index)
    if common is None or len(common) < 15:
        return
    common = common.sort_values()

    pm = pd.DataFrame({a: prices[a].loc[common] for a in prices})
    ret10 = pm.pct_change(10)

    # Compute congressional sector boost
    sector_boost = {a: 0.0 for a in ASSETS}
    if not congress.empty and "ticker" in congress.columns and "type" in congress.columns:
        buys = congress[congress["type"].str.lower().str.contains("buy|purchase", na=False)]
        for _, row in buys.iterrows():
            ticker = row.get("ticker", "")
            if ticker in TICKER_TO_SECTOR:
                sector = TICKER_TO_SECTOR[ticker]
                sector_boost[sector] += 0.02  # +2% bonus per congressional buy

    current_holding = None
    rotation_day = 0
    entry_price = None

    for i in range(12, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        rotation_day += 1

        if current_holding and entry_price:
            curr = float(pm[current_holding].iloc[i])
            pnl_pct = (curr - entry_price) / entry_price
            if pnl_pct <= -0.03:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
                current_holding = None
                entry_price = None
                rotation_day = 0
                continue

        if rotation_day < 3 and current_holding is not None:
            continue

        spy_ret = float(ret10["SPY"].iloc[i]) if pd.notna(ret10["SPY"].iloc[i]) else 0

        best_asset = None
        best_score = 0

        for asset in ASSETS:
            asset_ret = float(ret10[asset].iloc[i]) if pd.notna(ret10[asset].iloc[i]) else 0
            alpha = asset_ret - spy_ret + sector_boost.get(asset, 0)
            if alpha > best_score:
                best_score = alpha
                best_asset = asset

        target = best_asset

        if target != current_holding:
            if current_holding:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
            if target:
                result = portfolio.buy(target, dollars=portfolio.cash * 0.9, date=date_str)
                if result:
                    entry_price = float(pm[target].iloc[i])
            current_holding = target
            rotation_day = 0

    if current_holding:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(current_holding, all_shares=True, date=last_date)
