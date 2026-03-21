"""
Trend Pullback Hybrid — buy the deepest pullback within an established uptrend.

Thesis: Pure momentum chases tops. Pure mean-reversion buys falling knives. The sweet
spot is BOTH: buy an asset that's in an uptrend (20-day return > 0, above 20d MA) but
just had a short-term pullback (3-day return < -1%). This "buying the dip in a trend"
captures trend continuation using mean-reversion for entry timing.

Scan 7 diverse ETFs daily:
1. 20-day return > 0 (confirmed uptrend)
2. Price > 20-day MA (structural support)
3. 3-day return < -1% (short-term pullback)
4. Among qualifying ETFs, buy the one with the deepest 3-day pullback (best snap-back)

Hold 5 days or until recovery. This approach works in both trending and choppy markets
because it only enters on pullbacks (avoids buying tops) and requires a trend (avoids
falling knives).
"""

import pandas as pd
import numpy as np

UNIVERSE = ["QQQ", "SOXX", "XLF", "XLE", "XLI", "SLV", "EEM"]

STRATEGY = {
    "name": "Trend Pullback Hybrid",
    "hypothesis": "Buy the deepest 3-day pullback in an established uptrend (20d return > 0, above 20d MA). Combines trend following with mean-reversion entry timing.",
    "universe": UNIVERSE + ["SPY"],
    "entry": "Buy ETF with 20d return > 0 AND above 20d MA AND 3d return < -1%. Deepest pullback wins.",
    "exit": "Sell after 5 days or +3%/-2% stop",
    "position_size": "85% of capital per trade",
    "eccentricity": "Hybrid trend + mean-reversion approach across 7 diverse ETFs. Neither pure momentum nor pure contrarian — targets the sweet spot of 'dip within uptrend'.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    all_prices = {}
    for ticker in UNIVERSE:
        df = data_fetcher.get_prices(ticker, start=start_date, end=end_date)
        if not df.empty and "Close" in df.columns:
            s = df["Close"].dropna()
            s.index = pd.to_datetime(s.index)
            all_prices[ticker] = s

    if len(all_prices) < 4:
        return

    common = None
    for s in all_prices.values():
        common = s.index if common is None else common.intersection(s.index)
    if common is None or len(common) < 25:
        return
    common = common.sort_values()

    pm = pd.DataFrame({t: all_prices[t].loc[common] for t in all_prices})
    ret_3d = pm.pct_change(3)
    ret_20d = pm.pct_change(20)
    ma_20d = pm.rolling(20).mean()

    in_trade = False
    trade_ticker = None
    entry_price = None
    days_held = 0

    for i in range(25, len(common)):
        date_str = common[i].strftime("%Y-%m-%d")

        if in_trade:
            days_held += 1
            curr = float(pm[trade_ticker].iloc[i])
            pnl_pct = (curr - entry_price) / entry_price

            if days_held >= 5 or pnl_pct >= 0.03 or pnl_pct <= -0.02:
                portfolio.sell(trade_ticker, all_shares=True, date=date_str)
                in_trade = False
                trade_ticker = None
                entry_price = None
                days_held = 0

        elif not in_trade:
            best_ticker = None
            deepest_pullback = 0  # Most negative 3d return among qualifiers

            for ticker in all_prices:
                price = float(pm[ticker].iloc[i])
                r3 = float(ret_3d[ticker].iloc[i]) if pd.notna(ret_3d[ticker].iloc[i]) else 0
                r20 = float(ret_20d[ticker].iloc[i]) if pd.notna(ret_20d[ticker].iloc[i]) else 0
                ma = float(ma_20d[ticker].iloc[i]) if pd.notna(ma_20d[ticker].iloc[i]) else price

                # Uptrend + pullback
                if r20 > 0 and price > ma and r3 < -0.01:
                    if r3 < deepest_pullback:
                        deepest_pullback = r3
                        best_ticker = ticker

            if best_ticker:
                price = float(pm[best_ticker].iloc[i])
                result = portfolio.buy(best_ticker, dollars=portfolio.cash * 0.85, date=date_str)
                if result:
                    in_trade = True
                    trade_ticker = best_ticker
                    entry_price = price
                    days_held = 0

    if in_trade:
        last_date = common[-1].strftime("%Y-%m-%d")
        portfolio.sell(trade_ticker, all_shares=True, date=last_date)
