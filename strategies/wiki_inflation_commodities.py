"""
Wiki Inflation Commodities — Wikipedia inflation attention drives commodity allocation.

When Wikipedia pageviews for "Inflation" are above their 30-day rolling mean, public
concern about inflation is elevated → commodities (SLV, GDX) benefit.
When inflation attention is low → buy SOXX (growth tech, benefits from stable prices).
When moderate → buy XLF (banks adapt to moderate inflation).

Three signals:
1. Wikipedia "Inflation" pageview z-score vs 30-day mean
2. 5-day momentum of selected asset (confirmation)
3. Asset relative strength vs SPY (secondary ranking)
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Wiki Inflation Commodities",
    "hypothesis": "Wikipedia inflation attention predicts commodity outperformance. High attention = SLV/GDX, low = SOXX, moderate = XLF.",
    "universe": ["SLV", "GDX", "SOXX", "XLF", "SPY"],
    "entry": "High inflation attention → best of SLV/GDX. Low → SOXX. Moderate → XLF. 3-day rotation.",
    "exit": "Rotate every 3 days",
    "position_size": "90% of capital",
    "eccentricity": "Wikipedia inflation pageviews as a leading indicator for commodity vs tech allocation. Public concern about inflation leads price moves.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    wiki = data_fetcher.get_wikipedia_pageviews("Inflation")

    prices = {}
    for a in ["SLV", "GDX", "SOXX", "XLF", "SPY"]:
        df = data_fetcher.get_prices(a, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            prices[a] = s

    if len(prices) < 5 or wiki.empty:
        return

    wiki.index = pd.to_datetime(wiki.index)

    common = None
    for a in ["SLV", "GDX", "SOXX", "XLF", "SPY"]:
        common = prices[a].index if common is None else common.intersection(prices[a].index)
    if common is None or len(common) < 15:
        return
    common = common.sort_values()

    # Align wiki to trading days
    wiki_aligned = wiki.reindex(common, method="ffill")
    wiki_mean30 = wiki_aligned.rolling(30).mean()
    wiki_std30 = wiki_aligned.rolling(30).std()
    wiki_zscore = (wiki_aligned - wiki_mean30) / wiki_std30

    pm = pd.DataFrame({a: prices[a].loc[common] for a in prices})
    ret5 = pm.pct_change(5)
    ret10 = pm.pct_change(10)

    current_holding = None
    rotation_day = 0

    for i in range(35, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        rotation_day += 1
        if rotation_day < 3 and current_holding is not None:
            continue

        wz = float(wiki_zscore.iloc[i]) if pd.notna(wiki_zscore.iloc[i]) else 0
        spy_ret = float(ret10["SPY"].iloc[i]) if pd.notna(ret10["SPY"].iloc[i]) else 0

        if wz > 0.5:
            # High inflation attention → commodities
            slv_alpha = float(ret10["SLV"].iloc[i]) - spy_ret if pd.notna(ret10["SLV"].iloc[i]) else 0
            gdx_alpha = float(ret10["GDX"].iloc[i]) - spy_ret if pd.notna(ret10["GDX"].iloc[i]) else 0
            target = "SLV" if slv_alpha > gdx_alpha else "GDX"
        elif wz < -0.5:
            # Low inflation attention → growth
            target = "SOXX"
        else:
            # Moderate → banks or best rel strength
            best = None
            best_alpha = -999
            for a in ["SLV", "GDX", "SOXX", "XLF"]:
                ar = float(ret10[a].iloc[i]) if pd.notna(ret10[a].iloc[i]) else 0
                alpha = ar - spy_ret
                if alpha > best_alpha:
                    best_alpha = alpha
                    best = a
            target = best if best and best_alpha > 0 else "XLF"

        if target != current_holding:
            if current_holding:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
            portfolio.buy(target, dollars=portfolio.cash * 0.9, date=date_str)
            current_holding = target
            rotation_day = 0

    if current_holding:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(current_holding, all_shares=True, date=last_date)
