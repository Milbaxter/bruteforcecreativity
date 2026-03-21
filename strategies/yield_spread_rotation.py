"""
Yield Spread Rotation — 10Y-3M Treasury spread as economic regime signal.

When spread is positive (normal curve): economy healthy → SOXX (cyclical growth).
When spread is negative (inverted): recession signal → GDX (safe haven).
When near zero (flat): uncertainty → SLV (commodity hedge) or rel strength fallback.

Uses FRED T10Y3M series. 3-day rotation with -3% stop.
"""

import pandas as pd
import numpy as np

ASSETS = ["SOXX", "GDX", "SLV", "XLF"]

STRATEGY = {
    "name": "Yield Spread Rotation",
    "hypothesis": "T10Y3M yield spread as recession indicator. Positive = SOXX (growth). Negative = GDX (safety). Flat = rel strength.",
    "universe": ASSETS + ["SPY"],
    "entry": "SOXX when T10Y3M > 0.5, GDX when < -0.2, rel strength otherwise.",
    "exit": "Rotate every 3 days or -3% stop",
    "position_size": "90% of capital",
    "eccentricity": "Classic yield curve indicator applied to sector rotation (not usually used for ETF timing).",
}


def run(data_fetcher, portfolio, start_date, end_date):
    t10y3m = data_fetcher.get_fred_series("T10Y3M", start=start_date, end=end_date)

    prices = {}
    for a in ASSETS + ["SPY"]:
        df = data_fetcher.get_prices(a, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            prices[a] = s

    if len(prices) < 5 or t10y3m.empty:
        return

    t10y3m.index = pd.to_datetime(t10y3m.index)

    common = None
    for s in prices.values():
        common = s.index if common is None else common.intersection(s.index)
    if common is None or len(common) < 15:
        return
    common = common.sort_values()

    spread_aligned = t10y3m.reindex(common, method="ffill")
    pm = pd.DataFrame({a: prices[a].loc[common] for a in prices})
    ret10 = pm.pct_change(10)

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

        spread = float(spread_aligned.iloc[i]) if pd.notna(spread_aligned.iloc[i]) else 0
        spy_ret = float(ret10["SPY"].iloc[i]) if pd.notna(ret10["SPY"].iloc[i]) else 0

        if spread > 0.5:
            target = "SOXX"  # Healthy economy
        elif spread < -0.2:
            target = "GDX"   # Recession risk
        else:
            # Flat — use relative strength
            best = None
            best_alpha = 0
            for a in ASSETS:
                ar = float(ret10[a].iloc[i]) if pd.notna(ret10[a].iloc[i]) else 0
                alpha = ar - spy_ret
                if alpha > best_alpha:
                    best_alpha = alpha
                    best = a
            target = best if best else "SLV"

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
