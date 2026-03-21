"""
ETH/BTC Risk Signal — use the ETH/BTC ratio direction as a risk appetite barometer.

Thesis: Within crypto, ETH is the "risk-on" asset (higher beta, more speculative, tied
to DeFi/NFT activity) while BTC is the "quality" crypto (store of value, institutional
adoption). When ETH outperforms BTC (ratio rising), crypto risk appetite is elevated.
This historically LEADS traditional equity risk appetite by 1-3 days because crypto
markets run 24/7 and react faster than equities.

Rotation logic (every 3 days):
- ETH/BTC 7d ratio change > 0 AND BTC > 0 in 7d: Strong risk-on → QQQ
- ETH/BTC 7d ratio change < 0 AND BTC > 0: Risk-off flight to quality within crypto → GLD
- ETH/BTC 7d ratio change < 0 AND BTC < 0: Full risk-off → TLT
- ETH/BTC 7d ratio change > 0 AND BTC < 0: Speculative but weak base → sit in cash

Eccentricity: Using intra-crypto relative performance (ETH vs BTC) as a LEADING risk
indicator for traditional asset allocation. Nobody on Wall Street watches ETH/BTC to
decide whether to buy QQQ or TLT.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "ETH BTC Risk Signal",
    "hypothesis": "ETH/BTC ratio direction is a leading risk appetite indicator. ETH outperforming = risk-on (buy QQQ). BTC outperforming + declining crypto = risk-off (buy TLT/GLD). 3-day rotation.",
    "universe": ["QQQ", "TLT", "GLD", "BTC-USD", "ETH-USD", "SPY"],
    "entry": "Rotate based on ETH/BTC ratio direction + BTC absolute direction every 3 days",
    "exit": "Rotate every 3 days",
    "position_size": "90% of capital",
    "eccentricity": "Intra-crypto relative performance as leading indicator for traditional equity/bond allocation. Genuinely cross-domain — crypto micro-structure to equity macro.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    btc = data_fetcher.get_prices("BTC-USD", start=start_date, end=end_date)
    eth = data_fetcher.get_prices("ETH-USD", start=start_date, end=end_date)
    qqq = data_fetcher.get_prices("QQQ", start=start_date, end=end_date)
    tlt = data_fetcher.get_prices("TLT", start=start_date, end=end_date)
    gld = data_fetcher.get_prices("GLD", start=start_date, end=end_date)

    if btc.empty or eth.empty or qqq.empty or tlt.empty or gld.empty:
        return

    btc_close = btc["Close"].dropna()
    eth_close = eth["Close"].dropna()
    qqq_close = qqq["Close"].dropna()
    tlt_close = tlt["Close"].dropna()
    gld_close = gld["Close"].dropna()

    btc_close.index = pd.to_datetime(btc_close.index)
    eth_close.index = pd.to_datetime(eth_close.index)
    qqq_close.index = pd.to_datetime(qqq_close.index)
    tlt_close.index = pd.to_datetime(tlt_close.index)
    gld_close.index = pd.to_datetime(gld_close.index)

    # Use equity trading days as base, forward-fill crypto
    common = qqq_close.index.intersection(tlt_close.index).intersection(gld_close.index)
    btc_aligned = btc_close.reindex(common, method="ffill")
    eth_aligned = eth_close.reindex(common, method="ffill")

    if len(common) < 15:
        return

    # ETH/BTC ratio
    eth_btc_ratio = eth_aligned / btc_aligned

    # 7-day changes
    ratio_change7 = eth_btc_ratio.pct_change(7)
    btc_ret7 = btc_aligned.pct_change(7)

    current_holding = None
    rotation_day = 0

    for i in range(10, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        rotation_day += 1

        if rotation_day < 3 and current_holding is not None:
            continue

        rc = float(ratio_change7.iloc[i]) if pd.notna(ratio_change7.iloc[i]) else 0
        br = float(btc_ret7.iloc[i]) if pd.notna(btc_ret7.iloc[i]) else 0

        # Determine regime
        if rc > 0 and br > 0:
            target = "QQQ"     # Strong risk-on
        elif rc < 0 and br > 0:
            target = "GLD"     # Flight to quality within positive crypto
        elif rc < 0 and br < 0:
            target = "TLT"     # Full risk-off
        else:
            target = None      # Speculative but weak — cash

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
