"""
BTC Dominance Signal — Bitcoin market cap dominance as risk-on/off indicator.

Thesis: Bitcoin dominance (BTC market cap / total crypto market cap) acts as a "flight
to quality within crypto" indicator:
- Rising BTC dominance = money fleeing altcoins to BTC safety = risk-off signal
- Falling BTC dominance = money flowing into altcoins = altcoin season = risk-on signal

This LEADS traditional equity risk appetite because crypto reacts faster (24/7 markets,
retail-driven, no institutional rebalancing lag).

Allocation:
- BTC dominance falling (7d change < -0.5%): QQQ (risk-on, equities benefit)
- BTC dominance rising (7d change > +0.5%): TLT (risk-off, safety)
- Stable (±0.5%): SLV (neutral alternative alpha)

Use CoinGecko data for BTC market cap and total market cap.
Rotation every 3 days.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "BTC Dominance Signal",
    "hypothesis": "BTC dominance direction (BTC vs total crypto) is a leading risk indicator. Falling dominance = risk-on (QQQ). Rising = risk-off (TLT). Stable = SLV.",
    "universe": ["QQQ", "TLT", "SLV", "BTC-USD", "ETH-USD", "SPY"],
    "entry": "QQQ when BTC dominance falling, TLT when rising, SLV when stable. 3-day rotation.",
    "exit": "Rotate every 3 days",
    "position_size": "90% of capital",
    "eccentricity": "Intra-crypto capital flows (BTC vs altcoins) as a leading indicator for traditional asset allocation. Nobody watches BTC dominance to trade QQQ.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Compute BTC dominance proxy using BTC and ETH prices and market caps
    btc = data_fetcher.get_prices("BTC-USD", start=start_date, end=end_date)
    eth = data_fetcher.get_prices("ETH-USD", start=start_date, end=end_date)

    qqq = data_fetcher.get_prices("QQQ", start=start_date, end=end_date)
    tlt = data_fetcher.get_prices("TLT", start=start_date, end=end_date)
    slv = data_fetcher.get_prices("SLV", start=start_date, end=end_date)

    if btc.empty or eth.empty or qqq.empty or tlt.empty or slv.empty:
        return

    btc_close = btc["Close"].dropna()
    eth_close = eth["Close"].dropna()
    qqq_close = qqq["Close"].dropna()
    tlt_close = tlt["Close"].dropna()
    slv_close = slv["Close"].dropna()

    btc_close.index = pd.to_datetime(btc_close.index)
    eth_close.index = pd.to_datetime(eth_close.index)
    qqq_close.index = pd.to_datetime(qqq_close.index)
    tlt_close.index = pd.to_datetime(tlt_close.index)
    slv_close.index = pd.to_datetime(slv_close.index)

    common = qqq_close.index.intersection(tlt_close.index).intersection(slv_close.index)
    btc_aligned = btc_close.reindex(common, method="ffill")
    eth_aligned = eth_close.reindex(common, method="ffill")

    if len(common) < 15:
        return

    # BTC dominance proxy: BTC / (BTC + ETH * 10)
    # ETH * 10 approximates total altcoin market relative to BTC
    # Higher ratio = higher BTC dominance
    btc_dom = btc_aligned / (btc_aligned + eth_aligned * 10)
    dom_change_7d = btc_dom.diff(7)

    current_holding = None
    rotation_day = 0

    for i in range(10, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")
        rotation_day += 1

        if rotation_day < 3 and current_holding is not None:
            continue

        dc = float(dom_change_7d.iloc[i]) if pd.notna(dom_change_7d.iloc[i]) else 0

        if dc < -0.005:
            target = "QQQ"   # Altcoin season → risk-on
        elif dc > 0.005:
            target = "TLT"   # BTC flight to quality → risk-off
        else:
            target = "SLV"   # Stable → alternative alpha

        if target != current_holding:
            if current_holding:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
            portfolio.buy(target, dollars=portfolio.cash * 0.9, date=date_str)
            current_holding = target
            rotation_day = 0

    if current_holding:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(current_holding, all_shares=True, date=last_date)
