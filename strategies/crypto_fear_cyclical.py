"""
Crypto Fear Cyclical Trio — crypto fear regime for energy/transport/banks rotation.

Thesis: Apply the proven crypto fear/greed regime signal to a cyclical sector rotation:
- Extreme fear (< 25): Buy XLE (energy — defensive cyclical, inflation hedge)
- Moderate (25-55): Buy XLF (banks — benefit from normalization)
- Greed (> 55): Buy IYT (transports — leading economic indicator, max cyclical)

These three sectors are all cyclical but respond to different macro conditions:
- Energy: oil prices, geopolitics, supply constraints
- Banks: interest rates, credit quality, deal flow
- Transports: economic activity, consumer spending, supply chain

Each sector has performed well in different environments over the past 2+ years.
3-day rotation with momentum tiebreaker in neutral zone.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Crypto Fear Cyclical",
    "hypothesis": "Crypto fear/greed regime for XLE (fear), XLF (moderate), IYT (greed). Three cyclical sectors with different macro drivers.",
    "universe": ["XLE", "XLF", "IYT", "SPY"],
    "entry": "XLE when crypto fear < 25, XLF when 25-55, IYT when > 55. 3-day rotation.",
    "exit": "Rotate every 3 days",
    "position_size": "90% of capital",
    "eccentricity": "Crypto fear/greed applied to cyclical sector rotation (not the usual tech/gold/defense). Three sectors with genuinely different macro sensitivities.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    crypto_fg = data_fetcher.get_crypto_fear_greed(days=400)

    prices = {}
    for a in ["XLE", "XLF", "IYT"]:
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

        if fg < 25:
            target = "XLE"
        elif fg > 55:
            target = "IYT"
        else:
            # Moderate — momentum tiebreaker
            row = ret5.iloc[i].dropna()
            if not row.empty:
                best = row.idxmax()
                target = best if float(row[best]) > 0 else "XLF"
            else:
                target = "XLF"

        if target != current_holding:
            if current_holding:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
            portfolio.buy(target, dollars=portfolio.cash * 0.9, date=date_str)
            current_holding = target
            rotation_day = 0

    if current_holding:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(current_holding, all_shares=True, date=last_date)
