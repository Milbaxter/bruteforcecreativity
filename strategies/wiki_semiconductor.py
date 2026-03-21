"""
Wiki Semiconductor — Wikipedia semiconductor attention as SOXX catalyst signal.

When Wikipedia pageviews for "Semiconductor" are rising (above 30d mean), SOXX has
a narrative tailwind. Buy SOXX. When attention is flat/declining, rotate to best
relative strength among GDX/SLV/XLF.
"""

import pandas as pd
import numpy as np

ASSETS = ["SOXX", "GDX", "SLV", "XLF"]

STRATEGY = {
    "name": "Wiki Semiconductor",
    "hypothesis": "Wikipedia semiconductor attention rising = SOXX tailwind. Declining = rotate to GDX/SLV/XLF by rel strength.",
    "universe": ASSETS + ["SPY"],
    "entry": "SOXX when semiconductor wiki attention rising. Rel strength fallback otherwise.",
    "exit": "Rotate every 3 days or -3% stop",
    "position_size": "90% of capital",
    "eccentricity": "Wikipedia semiconductor attention as narrative catalyst signal for tech vs alternatives.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    wiki = data_fetcher.get_wikipedia_pageviews("Semiconductor")

    prices = {}
    for a in ASSETS + ["SPY"]:
        df = data_fetcher.get_prices(a, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            prices[a] = s

    if len(prices) < 5 or wiki.empty:
        return

    wiki.index = pd.to_datetime(wiki.index)

    common = None
    for s in prices.values():
        common = s.index if common is None else common.intersection(s.index)
    if common is None or len(common) < 35:
        return
    common = common.sort_values()

    wiki_aligned = wiki.reindex(common, method="ffill")
    wiki_mean30 = wiki_aligned.rolling(30).mean()

    pm = pd.DataFrame({a: prices[a].loc[common] for a in prices})
    ret10 = pm.pct_change(10)

    current_holding = None
    rotation_day = 0
    entry_price = None

    for i in range(35, len(common)):
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

        wv = float(wiki_aligned.iloc[i]) if pd.notna(wiki_aligned.iloc[i]) else 0
        wm = float(wiki_mean30.iloc[i]) if pd.notna(wiki_mean30.iloc[i]) else wv
        spy_ret = float(ret10["SPY"].iloc[i]) if pd.notna(ret10["SPY"].iloc[i]) else 0

        if wv > wm * 1.05:
            # Semiconductor attention rising → SOXX with momentum check
            soxx_alpha = float(ret10["SOXX"].iloc[i]) - spy_ret if pd.notna(ret10["SOXX"].iloc[i]) else 0
            if soxx_alpha > 0:
                target = "SOXX"
            else:
                # SOXX not outperforming despite attention → rel strength
                best = None
                best_alpha = 0
                for a in ASSETS:
                    ar = float(ret10[a].iloc[i]) if pd.notna(ret10[a].iloc[i]) else 0
                    alpha = ar - spy_ret
                    if alpha > best_alpha:
                        best_alpha = alpha
                        best = a
                target = best if best else "XLF"
        else:
            # Attention not rising → rel strength
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
