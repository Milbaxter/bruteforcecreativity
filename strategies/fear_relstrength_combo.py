"""
Fear + Relative Strength Combo — crypto fear filters regime, relative strength picks asset.

Thesis: Combining two validated signals:
1. Crypto fear/greed determines the OPPORTUNITY SET (which assets to consider)
2. SPY relative strength picks the SPECIFIC asset to buy

When fear (< 30): Only consider SLV and XLF (safe options). Buy whichever has higher
relative strength vs SPY.
When greed (> 60): Only consider QQQ and SOXX (aggressive options). Buy whichever
has higher relative strength vs SPY.
When moderate: Consider all four. Buy the one with highest relative strength.

This double-filtering reduces noise and increases conviction per trade.

Universe: QQQ, SOXX, SLV, XLF. 3-day rotation with -3% stop.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Fear RelStrength Combo",
    "hypothesis": "Crypto fear narrows the opportunity set; SPY relative strength picks the best asset within that set. Double signal = higher conviction.",
    "universe": ["QQQ", "SOXX", "SLV", "XLF", "SPY"],
    "entry": "Fear → choose from SLV/XLF by rel strength. Greed → choose from QQQ/SOXX. Moderate → all four.",
    "exit": "Rotate every 3 days or -3% stop",
    "position_size": "90% of capital",
    "eccentricity": "Two independent validated signals combined: crypto fear for regime, SPY relative strength for selection. Multiplicative signal quality.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    crypto_fg = data_fetcher.get_crypto_fear_greed(days=400)

    prices = {}
    for a in ["QQQ", "SOXX", "SLV", "XLF", "SPY"]:
        df = data_fetcher.get_prices(a, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            prices[a] = s

    if len(prices) < 5 or crypto_fg.empty:
        return

    crypto_fg.index = pd.to_datetime(crypto_fg.index)

    common = None
    for s in prices.values():
        common = s.index if common is None else common.intersection(s.index)
    if common is None or len(common) < 15:
        return
    common = common.sort_values()

    fg_aligned = crypto_fg.reindex(common, method="ffill")
    pm = pd.DataFrame({a: prices[a].loc[common] for a in prices})
    ret10 = pm.pct_change(10)

    current_holding = None
    rotation_day = 0
    entry_price = None

    for i in range(12, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        rotation_day += 1

        # Stop loss
        if current_holding and entry_price and current_holding != "SPY":
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

        fg = float(fg_aligned.iloc[i]) if pd.notna(fg_aligned.iloc[i]) else 50
        spy_ret = float(ret10["SPY"].iloc[i]) if pd.notna(ret10["SPY"].iloc[i]) else 0

        # Determine candidate set based on fear/greed
        if fg < 30:
            candidates = ["SLV", "XLF"]
        elif fg > 60:
            candidates = ["QQQ", "SOXX"]
        else:
            candidates = ["QQQ", "SOXX", "SLV", "XLF"]

        # Pick best relative strength from candidates
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
