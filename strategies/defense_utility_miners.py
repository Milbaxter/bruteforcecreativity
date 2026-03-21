"""
Defense Utility Miners — XAR/XLU/GDX rotation with crypto fear regime.

Thesis: Three genuinely different "alternative" sectors:
- XAR (defense): government spending, geopolitics, bipartisan support
- XLU (utilities): regulated returns, interest rate sensitivity, defensive
- GDX (gold miners): gold price leverage, inflation hedge, flight to safety

None of these are typical "growth" plays. They represent three different ways to NOT
be in tech while still making money. When crypto fear is high (risk-off everywhere),
GDX benefits from gold flight. When moderate, XAR benefits from stable government
spending. When greed is high, XLU benefits from rotation out of overheated growth.

Contrarian allocation:
- Fear (< 25): GDX (gold miners rally on fear)
- Moderate (25-55): XAR (steady defense spending, momentum-driven)
- Greed (> 55): XLU (defensive rotation as growth peaks)
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Defense Utility Miners",
    "hypothesis": "XAR/XLU/GDX rotation with crypto fear: GDX on fear (gold rush), XAR moderate (steady defense), XLU on greed (defensive rotation).",
    "universe": ["XAR", "XLU", "GDX", "SPY"],
    "entry": "GDX when crypto fear < 25, XAR when 25-55, XLU when > 55. 3-day rotation.",
    "exit": "Rotate every 3 days",
    "position_size": "90% of capital",
    "eccentricity": "Three non-tech, non-growth sectors (defense, utilities, gold miners) with crypto fear regime. Completely orthogonal to typical equity strategies.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    crypto_fg = data_fetcher.get_crypto_fear_greed(days=400)

    prices = {}
    for a in ["XAR", "XLU", "GDX"]:
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
            target = "GDX"
        elif fg > 55:
            target = "XLU"
        else:
            # Moderate — momentum tiebreaker among all three
            row = ret5.iloc[i].dropna()
            if not row.empty:
                best = row.idxmax()
                target = best if float(row[best]) > 0 else "XAR"
            else:
                target = "XAR"

        if target != current_holding:
            if current_holding:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
            portfolio.buy(target, dollars=portfolio.cash * 0.9, date=date_str)
            current_holding = target
            rotation_day = 0

    if current_holding:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(current_holding, all_shares=True, date=last_date)
