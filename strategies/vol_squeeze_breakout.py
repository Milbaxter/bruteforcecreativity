"""
Volatility Squeeze Breakout
When daily range contracts (squeeze), the next directional breakout tends to be powerful.
Buy when price breaks above the 5-day high after a volatility squeeze.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Volatility Squeeze Breakout",
    "hypothesis": "Low volatility periods (squeeze) are followed by expansion. When QQQ/SPY daily range contracts below 0.8% average, the subsequent breakout above the 5-day high captures directional moves. Combining with VIX filter avoids breakouts during high-fear regimes.",
    "universe": ["QQQ", "SPY"],
    "entry": "5-day avg daily range < 0.8% (squeeze) + close breaks above 5-day high + VIX < 22",
    "exit": "3 trading days or +2% take profit or -1.5% stop loss",
    "position_size": "85% of capital per trade, prefer QQQ for higher beta",
    "eccentricity": "Volatility structure play — exploits the squeeze-to-expansion cycle at a micro level too fast and too small for institutional vol desks to trade directly in equity",
}


def run(data_fetcher, portfolio, start_date, end_date):
    prices_qqq = data_fetcher.get_prices("QQQ", start=start_date, end=end_date)
    prices_spy = data_fetcher.get_prices("SPY", start=start_date, end=end_date)
    vix = data_fetcher.get_vix(start=start_date, end=end_date)

    for df in [prices_qqq, prices_spy]:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

    if prices_qqq.empty:
        return

    qqq = prices_qqq
    spy = prices_spy

    # Daily range as percentage of close
    qqq_range_pct = (qqq["High"] - qqq["Low"]) / qqq["Close"] * 100
    spy_range_pct = (spy["High"] - spy["Low"]) / spy["Close"] * 100

    # 5-day average range
    qqq_avg_range = qqq_range_pct.rolling(5).mean()
    spy_avg_range = spy_range_pct.rolling(5).mean()

    # 5-day high
    qqq_high5 = qqq["High"].rolling(5).max()
    spy_high5 = spy["High"].rolling(5).max()

    trading_days = qqq.index.tolist()
    vix_aligned = vix.reindex(pd.DatetimeIndex(trading_days), method="ffill")

    in_position = False
    entry_price = None
    entry_idx = None
    entry_ticker = None

    for i in range(10, len(trading_days)):
        date = trading_days[i]
        date_str = date.strftime("%Y-%m-%d")

        # Exit management
        if in_position:
            if entry_ticker == "QQQ":
                current = float(qqq["Close"].loc[date])
            else:
                current = float(spy["Close"].loc[date])

            pct = (current - entry_price) / entry_price
            days_held = i - entry_idx

            if pct >= 0.02 or pct <= -0.015 or days_held >= 3:
                portfolio.sell(entry_ticker, all_shares=True, date=date_str)
                in_position = False
                entry_price = None
                entry_idx = None
                entry_ticker = None
            continue

        # VIX filter
        vix_val = float(vix_aligned.loc[date]) if date in vix_aligned.index and not pd.isna(vix_aligned.loc[date]) else 15

        if vix_val >= 22:
            continue

        # Check QQQ squeeze breakout
        avg_r = float(qqq_avg_range.loc[date]) if not pd.isna(qqq_avg_range.loc[date]) else 999
        high5 = float(qqq_high5.loc[date]) if not pd.isna(qqq_high5.loc[date]) else 0
        close = float(qqq["Close"].loc[date])

        # Previous day's 5-day high (to check if today breaks out)
        if i > 0:
            prev_date = trading_days[i - 1]
            prev_high5 = float(qqq_high5.loc[prev_date]) if not pd.isna(qqq_high5.loc[prev_date]) else 0
        else:
            prev_high5 = 0

        if avg_r < 0.8 and close > prev_high5 and prev_high5 > 0:
            dollars = portfolio.cash * 0.85
            result = portfolio.buy("QQQ", dollars=dollars, date=date_str)
            if result:
                in_position = True
                entry_price = result["exec_price"]
                entry_idx = i
                entry_ticker = "QQQ"
                continue

        # Check SPY as fallback
        spy_avg_r = float(spy_avg_range.loc[date]) if date in spy_avg_range.index and not pd.isna(spy_avg_range.loc[date]) else 999
        spy_h5 = float(spy_high5.loc[date]) if date in spy_high5.index and not pd.isna(spy_high5.loc[date]) else 0
        spy_close = float(spy["Close"].loc[date])

        if i > 0:
            prev_spy_h5 = float(spy_high5.loc[prev_date]) if prev_date in spy_high5.index and not pd.isna(spy_high5.loc[prev_date]) else 0
        else:
            prev_spy_h5 = 0

        if spy_avg_r < 0.7 and spy_close > prev_spy_h5 and prev_spy_h5 > 0:
            dollars = portfolio.cash * 0.85
            result = portfolio.buy("SPY", dollars=dollars, date=date_str)
            if result:
                in_position = True
                entry_price = result["exec_price"]
                entry_idx = i
                entry_ticker = "SPY"
