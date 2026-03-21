"""
Multi-Regime Score — three regime signals combined into composite risk score.

Thesis: Any single regime signal is noisy. Combining three INDEPENDENT regime signals
reduces false positives dramatically:
1. VIX level: < 18 = +1 (calm), 18-25 = 0, > 25 = -1 (stressed)
2. Dollar direction (UUP 7d): falling = +1 (risk-on), rising = -1 (risk-off)
3. Crypto fear/greed: > 55 = +1 (greed), 25-55 = 0, < 25 = -1 (fear)

Composite score ranges from -3 (max fear) to +3 (max greed):
- Score >= 2: QQQ (strong risk-on consensus)
- Score == 1: SLV (moderate risk-on with commodity alpha)
- Score == 0: XLF (neutral — banks in normal conditions)
- Score <= -1: TLT (risk-off consensus)

Three signals must AGREE for extreme allocations, reducing whipsaw.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Multi Regime Score",
    "hypothesis": "VIX + dollar + crypto fear combined into composite score. Score >= 2: QQQ. Score 1: SLV. Score 0: XLF. Score <= -1: TLT.",
    "universe": ["QQQ", "SLV", "XLF", "TLT", "UUP", "SPY"],
    "entry": "Allocate based on composite score from 3 independent regime signals. 3-day rotation.",
    "exit": "Rotate every 3 days",
    "position_size": "90% of capital",
    "eccentricity": "Three independent regime signals (VIX, dollar, crypto fear) create a robust composite. Agreement across signals = higher conviction.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    vix = data_fetcher.get_vix(start=start_date, end=end_date)
    crypto_fg = data_fetcher.get_crypto_fear_greed(days=400)

    prices = {}
    for a in ["QQQ", "SLV", "XLF", "TLT", "UUP"]:
        df = data_fetcher.get_prices(a, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            prices[a] = s

    if len(prices) < 5 or vix.empty or crypto_fg.empty:
        return

    vix.index = pd.to_datetime(vix.index)
    crypto_fg.index = pd.to_datetime(crypto_fg.index)

    common = None
    for a in ["QQQ", "SLV", "XLF", "TLT"]:
        common = prices[a].index if common is None else common.intersection(prices[a].index)
    common = common.intersection(vix.index)
    if common is None or len(common) < 12:
        return
    common = common.sort_values()

    fg_aligned = crypto_fg.reindex(common, method="ffill")
    uup_aligned = prices["UUP"].reindex(common, method="ffill")
    uup_ret7 = uup_aligned.pct_change(7)

    current_holding = None
    rotation_day = 0

    for i in range(9, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        rotation_day += 1

        if rotation_day < 3 and current_holding is not None:
            continue

        # VIX signal
        v = float(vix.loc[common[i]])
        vix_score = 1 if v < 18 else (-1 if v > 25 else 0)

        # Dollar signal
        uup_r = float(uup_ret7.iloc[i]) if pd.notna(uup_ret7.iloc[i]) else 0
        dollar_score = 1 if uup_r < -0.002 else (-1 if uup_r > 0.002 else 0)

        # Crypto fear/greed signal
        fg = float(fg_aligned.iloc[i]) if pd.notna(fg_aligned.iloc[i]) else 50
        fg_score = 1 if fg > 55 else (-1 if fg < 25 else 0)

        # Composite score
        score = vix_score + dollar_score + fg_score

        if score >= 2:
            target = "QQQ"
        elif score == 1:
            target = "SLV"
        elif score == 0:
            target = "XLF"
        else:
            target = "TLT"

        if target != current_holding:
            if current_holding:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
            portfolio.buy(target, dollars=portfolio.cash * 0.9, date=date_str)
            current_holding = target
            rotation_day = 0

    if current_holding:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(current_holding, all_shares=True, date=last_date)
