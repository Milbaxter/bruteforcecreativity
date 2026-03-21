"""
Weather Relative Strength — weather extremes boost commodity relative strength.

When temperatures are extreme (very hot or very cold) in major US cities, energy demand
spikes and commodity prices tend to rise. Use this as a FILTER: when weather is extreme,
ONLY consider commodity-linked assets (SLV, GDX). When weather is normal, consider all
four assets.

This adds a physical-world signal to the relative strength framework.
Weather data from Open-Meteo for Chicago (represents Midwest heating/cooling demand).
"""

import pandas as pd
import numpy as np

ASSETS = ["SLV", "XLF", "SOXX", "GDX"]

STRATEGY = {
    "name": "Weather Rel Strength",
    "hypothesis": "Extreme weather (hot/cold) boosts commodity relative strength. Weather filter + SPY relative strength rotation.",
    "universe": ASSETS + ["SPY"],
    "entry": "Extreme weather: only SLV/GDX by rel strength. Normal weather: all 4 by rel strength.",
    "exit": "Rotate every 3 days or -3% stop",
    "position_size": "90% of capital",
    "eccentricity": "Physical weather data as regime filter for commodity vs equity allocation within relative strength framework.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Chicago weather (major heating/cooling demand center)
    try:
        weather = data_fetcher.get_weather_history(41.88, -87.63)  # Chicago
        has_weather = not weather.empty and "temp_max" in weather.columns
    except Exception:
        has_weather = False

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

    # Align weather to trading days
    extreme_weather = pd.Series(False, index=common)
    if has_weather:
        weather.index = pd.to_datetime(weather.index)
        temp_max_aligned = weather["temp_max"].reindex(common, method="ffill")
        temp_min_aligned = weather["temp_min"].reindex(common, method="ffill") if "temp_min" in weather.columns else temp_max_aligned
        extreme_weather = (temp_max_aligned > 35) | (temp_min_aligned < -5)  # Celsius: >95°F or <23°F

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
        is_extreme = bool(extreme_weather.iloc[i]) if pd.notna(extreme_weather.iloc[i]) else False

        # Determine candidate set
        candidates = ["SLV", "GDX"] if is_extreme else ASSETS

        best_asset = None
        best_alpha = 0

        for asset in candidates:
            asset_ret = float(ret10[asset].iloc[i]) if pd.notna(ret10[asset].iloc[i]) else 0
            alpha = asset_ret - spy_ret
            if alpha > best_alpha:
                best_alpha = alpha
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
