"""
Claims Rotation — initial jobless claims as labor market regime signal.

ICSA (initial claims) from FRED:
- Claims falling (4-week avg declining): labor market strengthening → SOXX
- Claims rising (4-week avg rising): labor market weakening → GDX
- Stable: relative strength

Combined with sector relative strength for asset selection.
"""

import pandas as pd
import numpy as np

ASSETS = ["SOXX", "GDX", "SLV", "XLF"]

STRATEGY = {
    "name": "Claims Rotation",
    "hypothesis": "Jobless claims direction: falling = SOXX (strong labor), rising = GDX (safety). Weekly labor data as economic regime.",
    "universe": ASSETS + ["SPY"],
    "entry": "SOXX on improving claims, GDX on worsening, rel strength when stable.",
    "exit": "Rotate every 3 days or -3% stop",
    "position_size": "90% of capital",
    "eccentricity": "FRED initial jobless claims as real-time economic health signal for sector rotation.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    claims = data_fetcher.get_fred_series("ICSA", start=start_date, end=end_date)

    prices = {}
    for a in ASSETS + ["SPY"]:
        df = data_fetcher.get_prices(a, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            prices[a] = s

    if len(prices) < 5 or claims.empty:
        return

    claims.index = pd.to_datetime(claims.index)

    common = None
    for s in prices.values():
        common = s.index if common is None else common.intersection(s.index)
    if common is None or len(common) < 15:
        return
    common = common.sort_values()

    # 4-week moving average of claims, aligned to trading days
    claims_ma4 = claims.rolling(4).mean()
    claims_aligned = claims_ma4.reindex(common, method="ffill")
    claims_change = claims_aligned.diff(28)  # 4-week change

    pm = pd.DataFrame({a: prices[a].loc[common] for a in prices})
    ret10 = pm.pct_change(10)

    current_holding = None
    rotation_day = 0
    entry_price = None

    for i in range(30, len(common)):
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

        cc = float(claims_change.iloc[i]) if pd.notna(claims_change.iloc[i]) else 0
        spy_ret = float(ret10["SPY"].iloc[i]) if pd.notna(ret10["SPY"].iloc[i]) else 0

        if cc < -5000:
            # Claims improving significantly → growth
            target = "SOXX"
        elif cc > 10000:
            # Claims worsening → safe haven
            target = "GDX"
        else:
            # Stable — rel strength
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
