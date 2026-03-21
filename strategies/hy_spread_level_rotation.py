"""
HY Spread Level Rotation — high yield credit spread level as risk regime signal.

BAMLH0A0HYM2 from FRED = ICE BofA US High Yield OAS.
Tight spreads (< 3.5%): credit conditions easy → favor growth (SOXX).
Wide spreads (> 5%): credit stress → favor safe haven (GDX).
Normal (3.5-5%): relative strength among all four.
"""

import pandas as pd
import numpy as np

ASSETS = ["SOXX", "GDX", "SLV", "XLF"]

STRATEGY = {
    "name": "HY Spread Level Rotation",
    "hypothesis": "HY credit spread level: tight (<3.5%) = SOXX growth, wide (>5%) = GDX safety, normal = rel strength. Credit regime + sector rotation.",
    "universe": ASSETS + ["SPY"],
    "entry": "SOXX when HY spread tight, GDX when wide, rel strength when normal.",
    "exit": "Rotate every 3 days or -3% stop",
    "position_size": "90% of capital",
    "eccentricity": "FRED credit spread level as regime signal for sector allocation. Credit markets are smarter than equity markets.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    hy_spread = data_fetcher.get_fred_series("BAMLH0A0HYM2", start=start_date, end=end_date)

    prices = {}
    for a in ASSETS + ["SPY"]:
        df = data_fetcher.get_prices(a, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            prices[a] = s

    if len(prices) < 5 or hy_spread.empty:
        return

    hy_spread.index = pd.to_datetime(hy_spread.index)

    common = None
    for s in prices.values():
        common = s.index if common is None else common.intersection(s.index)
    if common is None or len(common) < 15:
        return
    common = common.sort_values()

    spread_aligned = hy_spread.reindex(common, method="ffill")
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

        spread = float(spread_aligned.iloc[i]) if pd.notna(spread_aligned.iloc[i]) else 4
        spy_ret = float(ret10["SPY"].iloc[i]) if pd.notna(ret10["SPY"].iloc[i]) else 0

        if spread < 3.5:
            target = "SOXX"  # Tight spreads = easy credit = growth
        elif spread > 5.0:
            target = "GDX"   # Wide spreads = stress = safe haven
        else:
            # Normal — relative strength
            best = None
            best_alpha = 0
            for a in ASSETS:
                ar = float(ret10[a].iloc[i]) if pd.notna(ret10[a].iloc[i]) else 0
                alpha = ar - spy_ret
                if alpha > best_alpha:
                    best_alpha = alpha
                    best = a
            target = best if best else "XLF"

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
