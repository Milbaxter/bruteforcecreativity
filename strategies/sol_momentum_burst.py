"""
SOL Momentum Burst — buy SOL-USD on momentum breakout (new 5d high)
with crypto fear/greed confirmation and BTC trend filter.

Pure crypto swing trade targeting SOL's tendency for sharp momentum phases
due to its smaller market cap relative to BTC/ETH.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "SOL Momentum Burst",
    "hypothesis": "SOL has higher beta than BTC/ETH and tends to have explosive momentum phases when crypto sentiment is positive. Buying breakouts to new 5-day highs when BTC is in an uptrend and crypto fear/greed is moderate captures these momentum bursts at a scale too small for institutional crypto desks.",
    "universe": ["SOL-USD", "BTC-USD"],
    "entry": "SOL makes new 5d high AND BTC above 10d MA AND crypto fear/greed between 30-70",
    "exit": "Sell after 5 days or on -5% stop loss or +10% profit target",
    "position_size": "90% of cash per trade",
    "eccentricity": "Direct altcoin momentum trading at $10K scale — crypto funds don't bother with SOL swing trades at this size. The fear/greed filter avoids buying into euphoria tops.",
}


def run(data_fetcher, portfolio, start_date, end_date):
    sol = data_fetcher.get_prices("SOL-USD", start=start_date, end=end_date)
    btc = data_fetcher.get_prices("BTC-USD", start=start_date, end=end_date)

    if isinstance(sol.columns, pd.MultiIndex):
        sol.columns = sol.columns.get_level_values(0)
    if isinstance(btc.columns, pd.MultiIndex):
        btc.columns = btc.columns.get_level_values(0)

    if sol.empty or btc.empty:
        return

    try:
        fear_greed = data_fetcher.get_crypto_fear_greed(days=400)
    except Exception:
        fear_greed = None

    trading_days = sorted(sol.index)
    if len(trading_days) < 15:
        return

    in_trade = False
    entry_price = None
    entry_idx = None
    max_hold = 5
    stop_loss = -0.05
    profit_target = 0.10

    for i in range(10, len(trading_days)):
        day = trading_days[i]
        date_str = day.strftime("%Y-%m-%d") if hasattr(day, "strftime") else str(day)[:10]

        sol_price = float(sol.loc[day, "Close"])

        if in_trade:
            # Check exit
            days_held = i - entry_idx
            pnl_pct = (sol_price - entry_price) / entry_price if entry_price > 0 else 0

            if pnl_pct >= profit_target or pnl_pct <= stop_loss or days_held >= max_hold:
                if "SOL-USD" in portfolio.positions:
                    portfolio.sell("SOL-USD", all_shares=True, date=date_str)
                in_trade = False
                entry_price = None
                entry_idx = None
        else:
            # Check entry conditions

            # 1. New 5d high
            sol_before = sol[sol.index <= day]
            if len(sol_before) < 6:
                continue
            recent_high = float(sol_before["Close"].iloc[-6:-1].max())
            if sol_price <= recent_high:
                continue  # not a new 5d high

            # 2. BTC above 10d MA
            btc_before = btc[btc.index <= day]
            if len(btc_before) < 10:
                continue
            btc_price = float(btc_before["Close"].iloc[-1])
            btc_ma = float(btc_before["Close"].iloc[-10:].mean())
            if btc_price < btc_ma:
                continue  # BTC not in uptrend

            # 3. Crypto fear/greed between 30-70
            if fear_greed is not None and not fear_greed.empty:
                fg_before = fear_greed[fear_greed.index <= day]
                if len(fg_before) > 0:
                    fg_val = float(fg_before.iloc[-1])
                    if fg_val < 30 or fg_val > 70:
                        continue  # extreme sentiment

            # Signal — buy SOL
            result = portfolio.buy("SOL-USD", dollars=portfolio.cash * 0.90, date=date_str)
            if result:
                in_trade = True
                entry_price = sol_price
                entry_idx = i

    # Close at end
    if in_trade and "SOL-USD" in portfolio.positions:
        end_str = trading_days[-1].strftime("%Y-%m-%d") if hasattr(trading_days[-1], "strftime") else str(trading_days[-1])[:10]
        portfolio.sell("SOL-USD", all_shares=True, date=end_str)
