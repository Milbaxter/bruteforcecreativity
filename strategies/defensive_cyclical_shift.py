"""
Defensive-to-Cyclical Shift — buy cyclicals when defensives crack and cyclicals lead.

Thesis: When the defensive/cyclical ratio (XLU+XLP vs XLI+XLY) drops sharply, it signals
a regime shift from risk-off to risk-on. This is a leading indicator because defensive
holdings are sold first as confidence returns, and the proceeds flow into cyclicals over
the next 3-7 days.

Three signals:
1. Defensive basket (avg XLU, XLP) 5-day return is negative (defensives selling off)
2. Cyclical basket (avg XLI, XLY) 5-day return is positive (cyclicals rallying)
3. The spread (cyclical return - defensive return) > 2% (meaningful divergence)

Buy the stronger cyclical. Sell after 5 days.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Defensive Cyclical Shift",
    "hypothesis": "When defensives (XLU/XLP) sell off AND cyclicals (XLI/XLY) rally, it's a regime shift. Buy the leading cyclical for 5 days.",
    "universe": ["XLU", "XLP", "XLI", "XLY", "SPY"],
    "entry": "Buy stronger cyclical when defensive 5d return < 0 AND cyclical 5d return > 0 AND spread > 2%",
    "exit": "Sell after 5 days or +3%/-2% stop",
    "position_size": "80% of capital per trade",
    "eccentricity": "Inter-sector regime shift detection via defensive/cyclical spread. Institutions rebalance slowly across these categories.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    tickers = ["XLU", "XLP", "XLI", "XLY"]
    prices = {}
    for t in tickers:
        df = data_fetcher.get_prices(t, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            prices[t] = s

    if len(prices) < 4:
        return

    # Common dates
    common = None
    for s in prices.values():
        common = s.index if common is None else common.intersection(s.index)
    if len(common) < 15:
        return
    common = common.sort_values()

    # Aligned data
    pm = pd.DataFrame({t: prices[t].loc[common] for t in prices})

    # 5-day returns
    ret5 = pm.pct_change(5)

    # Defensive and cyclical baskets
    def_ret = (ret5["XLU"] + ret5["XLP"]) / 2
    cyc_ret = (ret5["XLI"] + ret5["XLY"]) / 2
    spread = cyc_ret - def_ret

    in_trade = False
    trade_ticker = None
    entry_price = None
    days_held = 0

    for i in range(10, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")

        if in_trade:
            days_held += 1
            current_price = float(pm[trade_ticker].iloc[i])
            pnl_pct = (current_price - entry_price) / entry_price

            if days_held >= 5 or pnl_pct >= 0.03 or pnl_pct <= -0.02:
                portfolio.sell(trade_ticker, all_shares=True, date=date_str)
                in_trade = False
                trade_ticker = None
                entry_price = None
                days_held = 0

        elif not in_trade:
            dr = float(def_ret.iloc[i]) if pd.notna(def_ret.iloc[i]) else 0
            cr = float(cyc_ret.iloc[i]) if pd.notna(cyc_ret.iloc[i]) else 0
            sp = float(spread.iloc[i]) if pd.notna(spread.iloc[i]) else 0

            if dr < 0 and cr > 0 and sp > 0.02:
                # Buy the stronger cyclical
                xli_r = float(ret5["XLI"].iloc[i]) if pd.notna(ret5["XLI"].iloc[i]) else 0
                xly_r = float(ret5["XLY"].iloc[i]) if pd.notna(ret5["XLY"].iloc[i]) else 0
                pick = "XLI" if xli_r > xly_r else "XLY"
                pick_price = float(pm[pick].iloc[i])

                result = portfolio.buy(pick, dollars=portfolio.cash * 0.8, date=date_str)
                if result:
                    in_trade = True
                    trade_ticker = pick
                    entry_price = pick_price
                    days_held = 0

    if in_trade:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(trade_ticker, all_shares=True, date=last_date)
