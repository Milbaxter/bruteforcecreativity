"""
Country Dollar Rotation — international equity rotation filtered by dollar direction.

Thesis: When the US dollar weakens (UUP declining), international equities benefit from
currency tailwinds. Different countries benefit at different times depending on their
export exposure and local market dynamics. Rotate into the strongest country ETF.

When the dollar is STRONG (UUP rising), international equities face headwinds → stay in
SPY (US equities benefit from dollar strength via import cost reduction and foreign
capital inflows).

Three signals:
1. UUP 7-day return direction determines international vs domestic
2. Among candidates, 7-day momentum selects the winner
3. Only invest if winner has positive 7d return (avoid buying losers)

Universe: SPY (US), EWJ (Japan), VGK (Europe), FXI (China)
3-day rotation.
"""

import pandas as pd
import numpy as np

INTERNATIONAL = ["EWJ", "VGK", "FXI"]
ALL_ASSETS = ["SPY"] + INTERNATIONAL

STRATEGY = {
    "name": "Country Dollar Rotation",
    "hypothesis": "Dollar weakness = rotate into strongest international ETF. Dollar strength = stay in SPY. Currency tailwinds drive international equity outperformance.",
    "universe": ALL_ASSETS + ["UUP"],
    "entry": "If UUP 7d return < 0: buy strongest international ETF. If UUP 7d return > 0: buy SPY. 3-day rotation.",
    "exit": "Rotate every 3 days",
    "position_size": "90% of capital",
    "eccentricity": "Dollar direction as gating filter for international vs domestic rotation. Currency signal → country selection is a cross-domain approach.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    prices = {}
    for a in ALL_ASSETS + ["UUP"]:
        df = data_fetcher.get_prices(a, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            prices[a] = s

    if len(prices) < 5:
        return

    common = None
    for s in prices.values():
        common = s.index if common is None else common.intersection(s.index)
    if common is None or len(common) < 12:
        return
    common = common.sort_values()

    pm = pd.DataFrame({a: prices[a].loc[common] for a in prices})
    ret7 = pm.pct_change(7)

    current_holding = None
    rotation_day = 0

    for i in range(9, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        rotation_day += 1

        if rotation_day < 3 and current_holding is not None:
            continue

        uup_ret = float(ret7["UUP"].iloc[i]) if pd.notna(ret7["UUP"].iloc[i]) else 0

        if uup_ret > 0:
            # Dollar strong → US only
            spy_ret = float(ret7["SPY"].iloc[i]) if pd.notna(ret7["SPY"].iloc[i]) else 0
            target = "SPY" if spy_ret > 0 else None
        else:
            # Dollar weak → international rotation
            best = None
            best_ret = 0
            for ticker in INTERNATIONAL:
                r = float(ret7[ticker].iloc[i]) if pd.notna(ret7[ticker].iloc[i]) else 0
                if r > best_ret:
                    best_ret = r
                    best = ticker
            target = best  # None if all international markets are negative

        if target != current_holding:
            if current_holding:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
            if target:
                portfolio.buy(target, dollars=portfolio.cash * 0.9, date=date_str)
            current_holding = target
            rotation_day = 0

    if current_holding:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(current_holding, all_shares=True, date=last_date)
