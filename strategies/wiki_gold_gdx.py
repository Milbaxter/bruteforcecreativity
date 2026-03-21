"""
Wiki Gold GDX — Wikipedia gold attention + GDX momentum = gold miners trade.

When Wikipedia pageviews for "Gold" spike (attention signal) AND GDX has positive
5-day momentum AND price > 20d MA → buy GDX. The attention spike signals incoming
retail interest which drives further buying in an already-trending asset.

Combined with: when no gold signal, rotate to XLF (banks) based on 5d momentum
for continuous deployment. When neither has positive momentum, go to SLV.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Wiki Gold GDX",
    "hypothesis": "Wikipedia gold attention spike + GDX positive momentum = retail-driven continuation. XLF/SLV as fallback.",
    "universe": ["GDX", "XLF", "SLV", "SPY"],
    "entry": "GDX when gold wiki views rising + GDX 5d momentum + above 20d MA. XLF or SLV otherwise.",
    "exit": "Rotate every 3 days",
    "position_size": "90% of capital",
    "eccentricity": "Wikipedia gold attention as leading indicator for gold miners. Retail attention drives flows into GDX.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    wiki = data_fetcher.get_wikipedia_pageviews("Gold")

    prices = {}
    for a in ["GDX", "XLF", "SLV"]:
        df = data_fetcher.get_prices(a, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            prices[a] = s

    if len(prices) < 3 or wiki.empty:
        return

    wiki.index = pd.to_datetime(wiki.index)

    common = None
    for s in prices.values():
        common = s.index if common is None else common.intersection(s.index)
    if common is None or len(common) < 25:
        return
    common = common.sort_values()

    # Align wiki to trading days
    wiki_aligned = wiki.reindex(common, method="ffill")
    wiki_mean20 = wiki_aligned.rolling(20).mean()
    wiki_rising = wiki_aligned > wiki_mean20

    pm = pd.DataFrame({a: prices[a].loc[common] for a in prices})
    ret5 = pm.pct_change(5)
    ma20 = pm.rolling(20).mean()

    current_holding = None
    rotation_day = 0

    for i in range(25, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        rotation_day += 1

        if rotation_day < 3 and current_holding is not None:
            continue

        gdx_price = float(pm["GDX"].iloc[i])
        gdx_ret = float(ret5["GDX"].iloc[i]) if pd.notna(ret5["GDX"].iloc[i]) else 0
        gdx_ma = float(ma20["GDX"].iloc[i]) if pd.notna(ma20["GDX"].iloc[i]) else gdx_price
        wiki_hot = bool(wiki_rising.iloc[i]) if pd.notna(wiki_rising.iloc[i]) else False

        if wiki_hot and gdx_ret > 0 and gdx_price > gdx_ma:
            target = "GDX"
        else:
            # Fallback: best of XLF and SLV by 5d return
            xlf_r = float(ret5["XLF"].iloc[i]) if pd.notna(ret5["XLF"].iloc[i]) else 0
            slv_r = float(ret5["SLV"].iloc[i]) if pd.notna(ret5["SLV"].iloc[i]) else 0
            if xlf_r > slv_r and xlf_r > 0:
                target = "XLF"
            elif slv_r > 0:
                target = "SLV"
            else:
                target = "XLF"  # default

        if target != current_holding:
            if current_holding:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
            portfolio.buy(target, dollars=portfolio.cash * 0.9, date=date_str)
            current_holding = target
            rotation_day = 0

    if current_holding:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(current_holding, all_shares=True, date=last_date)
