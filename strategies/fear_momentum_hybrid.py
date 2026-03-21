"""
Fear Momentum Hybrid — crypto fear/greed + 5-day momentum as composite signal.

Thesis: The crypto fear/greed index works as a regime signal, and momentum works as a
timing signal. COMBINING them creates a stronger composite:
- Crypto fear + strong SOXX momentum = MAX signal (buy SOXX aggressively)
- Crypto greed + strong SLV momentum = buy SLV (contrarian hedging with momentum)
- Score each asset: (fear/greed weight) * (5d momentum rank)

Score calculation for each asset:
- SOXX gets higher weight when fear/greed is high (greed = risk-on)
- SLV gets higher weight when fear/greed is low (fear = hedge with momentum)
- XLF gets higher weight when fear/greed is moderate (banks in normal conditions)

Buy the asset with the highest composite score. 3-day rotation.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Fear Momentum Hybrid",
    "hypothesis": "Crypto fear/greed regime x momentum ranking = composite score. Best of both signals combined. SOXX/SLV/XLF rotation.",
    "universe": ["SOXX", "SLV", "XLF", "SPY"],
    "entry": "Buy asset with highest composite score (fear/greed weight x momentum rank). Rotate every 3 days.",
    "exit": "Rotate every 3 days",
    "position_size": "90% of capital",
    "eccentricity": "Multiplicative combination of regime signal (crypto fear) and timing signal (momentum). Composite scoring instead of simple threshold-based switching.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    crypto_fg = data_fetcher.get_crypto_fear_greed(days=400)

    prices = {}
    for a in ["SOXX", "SLV", "XLF"]:
        df = data_fetcher.get_prices(a, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            prices[a] = s

    if len(prices) < 3 or crypto_fg.empty:
        return

    crypto_fg.index = pd.to_datetime(crypto_fg.index)

    common = None
    for s in prices.values():
        common = s.index if common is None else common.intersection(s.index)
    if common is None or len(common) < 10:
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
        fg_norm = fg / 100.0  # 0 to 1

        # Compute composite scores
        scores = {}
        for asset in prices:
            momentum = float(ret5[asset].iloc[i]) if pd.notna(ret5[asset].iloc[i]) else 0

            if asset == "SOXX":
                # Higher weight when greed (risk-on)
                weight = 0.3 + fg_norm * 0.7  # 0.3 in fear, 1.0 in greed
            elif asset == "SLV":
                # Higher weight when fear (commodity hedge)
                weight = 1.0 - fg_norm * 0.7  # 1.0 in fear, 0.3 in greed
            else:  # XLF
                # Peak weight at moderate fear/greed
                weight = 1.0 - abs(fg_norm - 0.5) * 2  # 0 at extremes, 1 at 50
                weight = max(weight, 0.2)

            # Composite: weight * max(momentum, 0)
            # Only positive momentum contributes
            scores[asset] = weight * max(momentum, 0)

        # Buy best scorer, but must have positive score
        if scores:
            best = max(scores, key=scores.get)
            if scores[best] > 0:
                target = best
            else:
                # All negative momentum — use fear/greed regime alone
                if fg < 35:
                    target = "SLV"
                elif fg > 60:
                    target = "SOXX"
                else:
                    target = "XLF"
        else:
            target = current_holding

        if target and target != current_holding:
            if current_holding:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
            portfolio.buy(target, dollars=portfolio.cash * 0.9, date=date_str)
            current_holding = target
            rotation_day = 0

    if current_holding:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(current_holding, all_shares=True, date=last_date)
