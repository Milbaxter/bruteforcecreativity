"""
HY-Treasury Spread — HYG/TLT relative performance as credit risk appetite signal.

Thesis: The high-yield bond market is the smartest indicator of credit risk appetite.
When HYG (high yield) outperforms TLT (treasuries), credit is easing = risk-on.
When TLT outperforms HYG, credit is tightening = risk-off.

This is a REAL MONEY signal (not derived like VIX) — actual bond investors are
choosing between risky and safe bonds with their capital.

Allocation based on HYG/TLT 7-day relative return:
- HYG outperforming TLT by > 0.5%: Credit risk-on → buy QQQ
- TLT outperforming HYG by > 0.5%: Credit risk-off → buy SLV (commodity hedge)
- Within 0.5%: Neutral → buy XLF (banks benefit from credit normalization)

3-day rotation. -3% stop loss.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "HY Treasury Spread",
    "hypothesis": "HYG vs TLT relative return = credit risk appetite. HYG leading = risk-on (QQQ). TLT leading = risk-off (SLV). Neutral = XLF.",
    "universe": ["QQQ", "SLV", "XLF", "HYG", "TLT", "SPY"],
    "entry": "QQQ when HYG 7d return > TLT 7d return + 0.5%. SLV when TLT leads. XLF when neutral.",
    "exit": "Rotate every 3 days or -3% stop",
    "position_size": "90% of capital",
    "eccentricity": "Credit market signal (HYG vs TLT) for equity/commodity allocation. Bond investors' risk appetite is a leading signal for equity markets.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    prices = {}
    for a in ["QQQ", "SLV", "XLF", "HYG", "TLT"]:
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
    entry_price = None

    for i in range(9, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        rotation_day += 1

        # Stop loss
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

        hyg_ret = float(ret7["HYG"].iloc[i]) if pd.notna(ret7["HYG"].iloc[i]) else 0
        tlt_ret = float(ret7["TLT"].iloc[i]) if pd.notna(ret7["TLT"].iloc[i]) else 0
        spread = hyg_ret - tlt_ret

        if spread > 0.005:
            target = "QQQ"   # Credit risk-on
        elif spread < -0.005:
            target = "SLV"   # Credit risk-off
        else:
            target = "XLF"   # Neutral

        if target != current_holding:
            if current_holding:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
            result = portfolio.buy(target, dollars=portfolio.cash * 0.9, date=date_str)
            if result:
                entry_price = float(pm[target].iloc[i])
            current_holding = target
            rotation_day = 0

    if current_holding:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(current_holding, all_shares=True, date=last_date)
