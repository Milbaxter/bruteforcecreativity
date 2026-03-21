"""
Copper Silver Regime — Cu/Ag ratio direction as growth vs monetary demand signal.

Copper = pure industrial demand. Silver = hybrid (industrial + monetary/safe haven).
When copper outperforms silver (CPER/SLV ratio rising): industrial growth strong → SOXX.
When silver outperforms copper: monetary/safe haven demand → GDX.
Neutral → XLF (banks benefit from either environment).

Combined with SPY relative strength for final selection.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Copper Silver Regime",
    "hypothesis": "CPER/SLV ratio direction: rising = industrial growth (SOXX), falling = monetary demand (GDX). Neutral = XLF. Rel strength filter.",
    "universe": ["SOXX", "GDX", "XLF", "SLV", "CPER", "SPY"],
    "entry": "SOXX when Cu/Ag rising, GDX when falling, XLF when neutral. Rel strength confirmation.",
    "exit": "Rotate every 3 days or -3% stop",
    "position_size": "90% of capital",
    "eccentricity": "Copper/silver ratio as industrial vs monetary demand signal. Different from copper/gold (already tested).",
}


def run(data_fetcher, portfolio, start_date, end_date):
    prices = {}
    for a in ["SOXX", "GDX", "XLF", "SLV", "CPER", "SPY"]:
        df = data_fetcher.get_prices(a, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            prices[a] = s

    if "CPER" not in prices or "SLV" not in prices or len(prices) < 6:
        return

    common = None
    for s in prices.values():
        common = s.index if common is None else common.intersection(s.index)
    if common is None or len(common) < 15:
        return
    common = common.sort_values()

    pm = pd.DataFrame({a: prices[a].loc[common] for a in prices})
    ret10 = pm.pct_change(10)

    # Copper/Silver ratio
    cu_ag_ratio = pm["CPER"] / pm["SLV"]
    ratio_change7 = cu_ag_ratio.pct_change(7)

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

        rc = float(ratio_change7.iloc[i]) if pd.notna(ratio_change7.iloc[i]) else 0
        spy_ret = float(ret10["SPY"].iloc[i]) if pd.notna(ret10["SPY"].iloc[i]) else 0

        if rc > 0.01:
            # Industrial growth → SOXX (with rel strength check)
            soxx_alpha = float(ret10["SOXX"].iloc[i]) - spy_ret if pd.notna(ret10["SOXX"].iloc[i]) else 0
            target = "SOXX" if soxx_alpha > 0 else "XLF"
        elif rc < -0.01:
            # Monetary demand → GDX (with rel strength check)
            gdx_alpha = float(ret10["GDX"].iloc[i]) - spy_ret if pd.notna(ret10["GDX"].iloc[i]) else 0
            target = "GDX" if gdx_alpha > 0 else "SLV"
        else:
            # Neutral → best rel strength among all
            best = None
            best_alpha = 0
            for a in ["SOXX", "GDX", "XLF", "SLV"]:
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
