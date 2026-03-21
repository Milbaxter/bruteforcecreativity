"""
Yield Curve Sector Switch
Use 10Y Treasury yield direction to rotate between financials, tech, and bonds.
Rising yields favor financials, falling yields favor tech and bonds.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Yield Curve Sector Switch",
    "hypothesis": "Rising yields benefit financials (wider net interest margins), falling yields benefit tech (lower discount rates) and bonds (price appreciation). Yield direction is a leading signal for sector rotation.",
    "universe": ["XLF", "XLK", "TLT", "SPY"],
    "entry": "Rising 10Y yield (5-day change > 0 + above 50-day MA) → XLF. Falling yield → XLK or TLT (buy stronger). Flat → hold cash.",
    "exit": "Rotate every 5 trading days based on latest yield signal, -3% stop loss",
    "position_size": "90% of capital in selected ETF",
    "eccentricity": "Macro yield regime directly drives micro sector selection — a cross-domain approach that's too simplistic for institutional macro desks but perfectly sized for retail swing trading",
}


def run(data_fetcher, portfolio, start_date, end_date):
    # Fetch yield data (^TNX is 10Y yield)
    tnx = data_fetcher.get_prices("^TNX", start=start_date, end=end_date)
    prices_xlf = data_fetcher.get_prices("XLF", start=start_date, end=end_date)
    prices_xlk = data_fetcher.get_prices("XLK", start=start_date, end=end_date)
    prices_tlt = data_fetcher.get_prices("TLT", start=start_date, end=end_date)

    for df in [tnx, prices_xlf, prices_xlk, prices_tlt]:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

    if tnx.empty or prices_xlf.empty or prices_xlk.empty:
        return

    yield_close = tnx["Close"]
    xlf_close = prices_xlf["Close"]
    xlk_close = prices_xlk["Close"]
    tlt_close = prices_tlt["Close"] if not prices_tlt.empty else None

    # Yield signals
    yield_ma50 = yield_close.rolling(50).mean()
    yield_change5 = yield_close.diff(5)

    # Momentum signals for selection within falling-yield regime
    xlk_ret5 = xlk_close.pct_change(5)
    tlt_ret5 = tlt_close.pct_change(5) if tlt_close is not None else None

    trading_days = xlf_close.index.tolist()
    common = set(yield_close.index) & set(xlf_close.index)

    current_holding = None
    entry_price = None
    last_rotation = -999

    for i in range(55, len(trading_days)):
        date = trading_days[i]
        date_str = date.strftime("%Y-%m-%d")

        if date not in common:
            continue

        # Stop loss check
        if current_holding is not None and entry_price is not None:
            if current_holding == "XLF":
                current = float(xlf_close.loc[date])
            elif current_holding == "XLK":
                current = float(xlk_close.loc[date])
            elif current_holding == "TLT" and tlt_close is not None:
                current = float(tlt_close.loc[date])
            else:
                current = entry_price

            pct = (current - entry_price) / entry_price
            if pct <= -0.03:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
                current_holding = None
                entry_price = None
                last_rotation = i
                continue

        # Rotate every 5 days
        if i - last_rotation < 5:
            continue

        y_val = float(yield_close.loc[date])
        y_ma = float(yield_ma50.loc[date]) if not pd.isna(yield_ma50.loc[date]) else y_val
        y_chg = float(yield_change5.loc[date]) if not pd.isna(yield_change5.loc[date]) else 0

        # Determine target
        if y_chg > 0 and y_val > y_ma:
            # Rising yields → financials
            target = "XLF"
        elif y_chg < 0:
            # Falling yields → pick stronger of XLK or TLT
            xlk_mom = float(xlk_ret5.loc[date]) if date in xlk_ret5.index and not pd.isna(xlk_ret5.loc[date]) else 0
            tlt_mom = float(tlt_ret5.loc[date]) if tlt_ret5 is not None and date in tlt_ret5.index and not pd.isna(tlt_ret5.loc[date]) else 0

            if xlk_mom > tlt_mom:
                target = "XLK"
            else:
                target = "TLT"
        else:
            # Flat/uncertain — stay with current or go to XLK as default
            target = "XLK"

        # Only trade if target changed
        if target != current_holding:
            # Sell current
            if current_holding is not None:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
                current_holding = None

            # Buy new target
            dollars = portfolio.cash * 0.90
            result = portfolio.buy(target, dollars=dollars, date=date_str)
            if result:
                current_holding = target
                entry_price = result["exec_price"]

        last_rotation = i
