"""
Fear Miners Banks — simplest possible crypto fear rotation: GDX on fear, XLF on greed.

Only 2 assets, simple threshold. GDX (gold miners) rallies in fear environments.
XLF (banks) rallies in greed/calm environments. Momentum tiebreaker when neutral.

Fear < 35: GDX
Greed > 50: XLF
Neutral: momentum leader
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Fear Miners Banks",
    "hypothesis": "GDX on crypto fear < 35, XLF on greed > 50. Simplest possible fear/greed rotation. Two asset classes, opposite macro drivers.",
    "universe": ["GDX", "XLF", "SPY"],
    "entry": "GDX when fear < 35, XLF when > 50, momentum leader when neutral.",
    "exit": "Rotate every 3 days",
    "position_size": "90% of capital",
    "eccentricity": "Ultra-simple 2-asset crypto fear rotation. Gold miners vs banks = pure risk-on/off barbell.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    crypto_fg = data_fetcher.get_crypto_fear_greed(days=400)

    prices = {}
    for a in ["GDX", "XLF"]:
        df = data_fetcher.get_prices(a, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            prices[a] = s

    if len(prices) < 2 or crypto_fg.empty:
        return

    crypto_fg.index = pd.to_datetime(crypto_fg.index)

    common = prices["GDX"].index.intersection(prices["XLF"].index)
    if len(common) < 10:
        return
    common = common.sort_values()

    fg_aligned = crypto_fg.reindex(common, method="ffill")
    pm = pd.DataFrame({a: prices[a].loc[common] for a in prices})
    ret5 = pm.pct_change(5)

    current_holding = None
    rotation_day = 0

    for i in range(7, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        rotation_day += 1

        if rotation_day < 3 and current_holding is not None:
            continue

        fg = float(fg_aligned.iloc[i]) if pd.notna(fg_aligned.iloc[i]) else 50

        if fg < 35:
            target = "GDX"
        elif fg > 50:
            target = "XLF"
        else:
            gdx_r = float(ret5["GDX"].iloc[i]) if pd.notna(ret5["GDX"].iloc[i]) else 0
            xlf_r = float(ret5["XLF"].iloc[i]) if pd.notna(ret5["XLF"].iloc[i]) else 0
            target = "GDX" if gdx_r > xlf_r else "XLF"

        if target != current_holding:
            if current_holding:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
            portfolio.buy(target, dollars=portfolio.cash * 0.9, date=date_str)
            current_holding = target
            rotation_day = 0

    if current_holding:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(current_holding, all_shares=True, date=last_date)
