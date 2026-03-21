"""
Dollar Drop Commodity Burst — buy the strongest commodity ETF when the dollar weakens.

Thesis: Commodities are priced in USD, so dollar weakness mechanically boosts commodity
prices. But different commodities respond at different speeds — the one with the strongest
5-day momentum after a dollar drop tends to continue outperforming for 3-5 more days
because the dollar move takes time to fully propagate through physical commodity markets.

Three signals:
1. UUP (dollar ETF) 5-day return < -0.5% (dollar weakening)
2. At least one commodity ETF has 5-day return > +1% (momentum confirmation)
3. Dollar is below its 20-day MA (sustained weakness, not a one-day blip)

Universe: DBA (agriculture), USO (oil), GLD (gold), SLV (silver), UNG (nat gas), WEAT (wheat)
Buy the commodity ETF with the strongest 5-day momentum.
"""

import pandas as pd
import numpy as np

COMMODITIES = ["DBA", "USO", "GLD", "SLV", "UNG", "WEAT"]

STRATEGY = {
    "name": "Dollar Drop Commodity",
    "hypothesis": "Dollar weakness boosts commodity prices with a lag. Buy the strongest commodity momentum leader when dollar is weakening and below 20d MA.",
    "universe": COMMODITIES + ["UUP", "SPY"],
    "entry": "Buy strongest commodity when UUP 5d return < -0.5% AND best commodity 5d return > 1% AND UUP < 20d MA",
    "exit": "Sell after 5 days or +3%/-2% stop",
    "position_size": "80% of capital per trade",
    "eccentricity": "FX-to-commodity propagation delay with momentum selection across diverse commodities. Combines currency signal with commodity momentum ranking.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Fetch dollar ETF
    uup = data_fetcher.get_prices("UUP", start=start_date, end=end_date)
    if uup.empty:
        return

    uup_close = uup["Close"].dropna()
    uup_close.index = pd.to_datetime(uup_close.index)

    # Fetch commodity prices
    comm_prices = {}
    for c in COMMODITIES:
        df = data_fetcher.get_prices(c, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            comm_prices[c] = s

    if len(comm_prices) < 3:
        return

    # Find common dates
    common = uup_close.index
    for s in comm_prices.values():
        common = common.intersection(s.index)
    if len(common) < 25:
        return
    common = common.sort_values()

    # Build aligned data
    uup_c = uup_close.loc[common]
    comm_matrix = pd.DataFrame({c: comm_prices[c].loc[common] for c in comm_prices})

    # Signals
    uup_ret5 = uup_c.pct_change(5)
    uup_ma20 = uup_c.rolling(20).mean()
    comm_ret5 = comm_matrix.pct_change(5)

    in_trade = False
    trade_ticker = None
    entry_price = None
    days_held = 0

    for i in range(25, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")

        if in_trade:
            days_held += 1
            current_price = float(comm_matrix[trade_ticker].iloc[i])
            pnl_pct = (current_price - entry_price) / entry_price

            if days_held >= 5 or pnl_pct >= 0.03 or pnl_pct <= -0.02:
                portfolio.sell(trade_ticker, all_shares=True, date=date_str)
                in_trade = False
                trade_ticker = None
                entry_price = None
                days_held = 0

        elif not in_trade:
            uup_r = float(uup_ret5.iloc[i]) if pd.notna(uup_ret5.iloc[i]) else 0
            uup_price = float(uup_c.iloc[i])
            uup_ma = float(uup_ma20.iloc[i]) if pd.notna(uup_ma20.iloc[i]) else uup_price

            if uup_r >= -0.005 or uup_price >= uup_ma:
                continue

            # Dollar is weak — find strongest commodity
            row = comm_ret5.iloc[i].dropna()
            if row.empty:
                continue

            best_comm = row.idxmax()
            best_ret = float(row[best_comm])

            if best_ret > 0.01:
                best_price = float(comm_matrix[best_comm].iloc[i])
                result = portfolio.buy(best_comm, dollars=portfolio.cash * 0.8, date=date_str)
                if result:
                    in_trade = True
                    trade_ticker = best_comm
                    entry_price = best_price
                    days_held = 0

    # Close remaining
    if in_trade:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(trade_ticker, all_shares=True, date=last_date)
