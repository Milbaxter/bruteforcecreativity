"""
Google Silver Rush — buy SLV when Google Trends for "silver price" spike + momentum.

Silver is the most retail-driven commodity. When Google searches for "silver price"
spike, retail interest is surging. Combined with positive SLV momentum and trend
confirmation, this predicts continued upside for 5-7 days.

When no silver signal, fall back to relative strength rotation among XLF/SOXX/GDX.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Google Silver Rush",
    "hypothesis": "Google Trends silver spike + SLV momentum = retail-driven continuation. XLF/SOXX/GDX fallback.",
    "universe": ["SLV", "XLF", "SOXX", "GDX", "SPY"],
    "entry": "SLV when Google silver trends rising + positive momentum. Else rel strength rotation.",
    "exit": "Rotate every 3 days",
    "position_size": "90% of capital",
    "eccentricity": "Google Trends as retail attention signal for the most retail-driven commodity (silver). Attention drives flows → price.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Try to get Google Trends
    try:
        trends = data_fetcher.get_google_trends(["silver price"])
        has_trends = not trends.empty and "silver price" in trends.columns
    except Exception:
        has_trends = False

    prices = {}
    for a in ["SLV", "XLF", "SOXX", "GDX", "SPY"]:
        df = data_fetcher.get_prices(a, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            prices[a] = s

    if len(prices) < 5:
        return

    common = None
    for a in ["SLV", "XLF", "SOXX", "GDX", "SPY"]:
        if a in prices:
            common = prices[a].index if common is None else common.intersection(prices[a].index)
    if common is None or len(common) < 25:
        return
    common = common.sort_values()

    pm = pd.DataFrame({a: prices[a].loc[common] for a in prices if a in prices})
    ret5 = pm.pct_change(5)
    ret10 = pm.pct_change(10)
    ma20 = pm.rolling(20).mean()

    # Check if silver trends are rising
    silver_hot = False
    if has_trends:
        silver_data = trends["silver price"]
        if len(silver_data) >= 4:
            recent = silver_data.iloc[-2:]
            older = silver_data.iloc[-4:-2]
            silver_hot = float(recent.mean()) > float(older.mean()) * 1.1

    current_holding = None
    rotation_day = 0

    for i in range(25, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        rotation_day += 1

        if rotation_day < 3 and current_holding is not None:
            continue

        slv_ret = float(ret5["SLV"].iloc[i]) if pd.notna(ret5["SLV"].iloc[i]) else 0
        slv_price = float(pm["SLV"].iloc[i])
        slv_ma = float(ma20["SLV"].iloc[i]) if pd.notna(ma20["SLV"].iloc[i]) else slv_price

        # Silver signal: Google Trends hot + momentum + trend
        if silver_hot and slv_ret > 0 and slv_price > slv_ma:
            target = "SLV"
        else:
            # Fall back to relative strength
            spy_ret = float(ret10["SPY"].iloc[i]) if pd.notna(ret10["SPY"].iloc[i]) else 0
            best_asset = None
            best_alpha = 0

            for asset in ["SLV", "XLF", "SOXX", "GDX"]:
                asset_ret = float(ret10[asset].iloc[i]) if pd.notna(ret10[asset].iloc[i]) else 0
                alpha = asset_ret - spy_ret
                if alpha > best_alpha:
                    best_alpha = alpha
                    best_asset = asset

            target = best_asset if best_asset else "XLF"

        if target != current_holding:
            if current_holding:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
            portfolio.buy(target, dollars=portfolio.cash * 0.9, date=date_str)
            current_holding = target
            rotation_day = 0

    if current_holding:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(current_holding, all_shares=True, date=last_date)
