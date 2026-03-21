"""
Crypto Fear Silver Trio — crypto fear/greed regime for SLV/QQQ/XLF allocation.

Thesis: The crypto fear/greed index is a proven leading risk indicator (see Crypto Fear
Risk Indicator, a walk-forward validated winner). This strategy applies the SAME regime
signal to a DIFFERENT asset universe:
- Extreme fear (< 25): buy SLV (silver as safe haven + industrial demand hedge)
- Neutral (25-55): buy XLF (banks benefit from normalized conditions)
- Greed (> 55): buy QQQ (risk-on tech)

Silver replaces gold because: (1) silver is more volatile → bigger moves → more alpha,
(2) silver has industrial demand (solar, EV) giving it a growth component even in
defensive positioning, (3) it's less followed by institutions.

XLF replaces XLE because: (1) banks benefit from rate normalization during calm periods,
(2) energy is too correlated with macro risk, (3) banks have their own catalyst cycle.

3-day rotation with 5-day momentum tiebreaker when crypto fear/greed is in transition.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Crypto Fear Silver Trio",
    "hypothesis": "Crypto fear/greed as regime signal for SLV (fear), XLF (neutral), QQQ (greed). Novel asset universe with proven regime signal.",
    "universe": ["QQQ", "SLV", "XLF", "SPY"],
    "entry": "SLV when crypto fear < 25, XLF when 25-55, QQQ when > 55. 3-day rotation.",
    "exit": "Rotate every 3 days based on updated fear/greed level",
    "position_size": "90% of capital",
    "eccentricity": "Proven crypto fear/greed signal applied to novel SLV/QQQ/XLF universe. Silver as safe haven instead of gold, banks instead of energy.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Fetch crypto fear/greed
    crypto_fg = data_fetcher.get_crypto_fear_greed(days=400)

    qqq = data_fetcher.get_prices("QQQ", start=start_date, end=end_date)
    slv = data_fetcher.get_prices("SLV", start=start_date, end=end_date)
    xlf = data_fetcher.get_prices("XLF", start=start_date, end=end_date)

    if qqq.empty or slv.empty or xlf.empty or crypto_fg.empty:
        return

    qqq_close = qqq["Close"].dropna()
    slv_close = slv["Close"].dropna()
    xlf_close = xlf["Close"].dropna()

    qqq_close.index = pd.to_datetime(qqq_close.index)
    slv_close.index = pd.to_datetime(slv_close.index)
    xlf_close.index = pd.to_datetime(xlf_close.index)
    crypto_fg.index = pd.to_datetime(crypto_fg.index)

    common = qqq_close.index.intersection(slv_close.index).intersection(xlf_close.index)
    if len(common) < 10:
        return

    # Align crypto fear/greed to trading days
    fg_aligned = crypto_fg.reindex(common, method="ffill")

    # 5-day momentum for tiebreaker
    pm = pd.DataFrame({
        "QQQ": qqq_close.loc[common],
        "SLV": slv_close.loc[common],
        "XLF": xlf_close.loc[common],
    })
    ret5 = pm.pct_change(5)

    current_holding = None
    rotation_day = 0

    for i in range(7, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        rotation_day += 1

        if rotation_day < 3 and current_holding is not None:
            continue

        fg = float(fg_aligned.iloc[i]) if pd.notna(fg_aligned.iloc[i]) else 50

        # Regime-based allocation
        if fg < 25:
            target = "SLV"   # Fear → safe haven commodity
        elif fg > 55:
            target = "QQQ"   # Greed → risk-on tech
        else:
            # Neutral zone — use momentum tiebreaker
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
