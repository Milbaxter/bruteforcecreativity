"""
Crypto Fear Quad Rotation — crypto fear/greed regime across 4 assets with finer bins.

Thesis: Expanding on the validated crypto fear/greed regime signal with more granular
asset allocation based on four fear/greed levels:

- Extreme fear (< 20): TLT — maximum safety, risk-off dominating
- Fear (20-40): SLV — commodity hedge, moderate safety with upside
- Neutral-to-greedy (40-65): SOXX — growth cyclical, higher beta than QQQ
- Extreme greed (> 65): QQQ — broad tech, moderate risk-on

Adding a 5-day momentum confirmation: only switch if the new target has positive 5-day
momentum. If not, hold current position (avoid switching into a falling asset).

The 4 assets cover the full risk spectrum: safety (TLT) → commodity hedge (SLV) →
cyclical growth (SOXX) → broad tech (QQQ). Each responds differently to macro conditions.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Crypto Fear Quad",
    "hypothesis": "Crypto fear/greed with 4 levels: extreme fear→TLT, fear→SLV, neutral/greedy→SOXX, extreme greed→QQQ. Momentum confirmation before switching.",
    "universe": ["QQQ", "SOXX", "SLV", "TLT", "SPY"],
    "entry": "TLT (fear<20), SLV (20-40), SOXX (40-65), QQQ (>65). Only switch if target has positive 5d momentum.",
    "exit": "Rotate every 3 days with momentum confirmation",
    "position_size": "90% of capital",
    "eccentricity": "4-level crypto fear regime mapping to 4 different assets covering full risk spectrum. Finer granularity than 3-level approach.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    crypto_fg = data_fetcher.get_crypto_fear_greed(days=400)

    prices = {}
    for a in ["QQQ", "SOXX", "SLV", "TLT"]:
        df = data_fetcher.get_prices(a, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            prices[a] = s

    if len(prices) < 4 or crypto_fg.empty:
        return

    common = None
    for s in prices.values():
        common = s.index if common is None else common.intersection(s.index)
    if common is None or len(common) < 10:
        return
    common = common.sort_values()

    crypto_fg.index = pd.to_datetime(crypto_fg.index)
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

        # 4-level regime
        if fg < 20:
            target = "TLT"
        elif fg < 40:
            target = "SLV"
        elif fg < 65:
            target = "SOXX"
        else:
            target = "QQQ"

        # Momentum confirmation: only switch if target has positive 5d return
        if target != current_holding:
            target_ret = float(ret5[target].iloc[i]) if pd.notna(ret5[target].iloc[i]) else 0
            if target_ret <= 0 and current_holding is not None:
                # Target is falling — hold current position
                continue

        if target != current_holding:
            if current_holding:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
            portfolio.buy(target, dollars=portfolio.cash * 0.9, date=date_str)
            current_holding = target
            rotation_day = 0

    if current_holding:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(current_holding, all_shares=True, date=last_date)
