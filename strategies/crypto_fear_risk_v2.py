"""
Crypto Fear Risk Indicator v2
Faster rotation and adjusted thresholds. 2-day rotation, wider greed zone.
"""

import pandas as pd
import numpy as np

STRATEGY = {
    "name": "Crypto Fear Risk v2",
    "hypothesis": "Same cross-market thesis as v1 but with faster rotation (2 days), wider greed zone (>50), and 5-day momentum lookback for more responsive signal.",
    "universe": ["GLD", "QQQ", "XLE"],
    "entry": "Crypto F&G < 25 → GLD. F&G > 50 → best of QQQ/XLE by 5d momentum. Neutral → best of all 3 by 5d momentum.",
    "exit": "Rotate every 2 trading days, -3% stop loss",
    "position_size": "90% of capital in selected ETF",
    "eccentricity": "Faster-reacting version of crypto fear risk indicator — tighter rotation captures short-term regime shifts",
}


def run(data_fetcher, portfolio, start_date, end_date):
    prices_gld = data_fetcher.get_prices("GLD", start=start_date, end=end_date)
    prices_qqq = data_fetcher.get_prices("QQQ", start=start_date, end=end_date)
    prices_xle = data_fetcher.get_prices("XLE", start=start_date, end=end_date)

    for df in [prices_gld, prices_qqq, prices_xle]:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

    crypto_fg = data_fetcher.get_crypto_fear_greed(days=400)

    if prices_gld.empty or prices_qqq.empty or prices_xle.empty:
        return

    gld_close = prices_gld["Close"]
    qqq_close = prices_qqq["Close"]
    xle_close = prices_xle["Close"]

    # 5-day momentum (faster than v1's 7-day)
    gld_ret = gld_close.pct_change(5)
    qqq_ret = qqq_close.pct_change(5)
    xle_ret = xle_close.pct_change(5)

    trading_days = qqq_close.index.tolist()

    if isinstance(crypto_fg, pd.Series):
        fg_aligned = crypto_fg.reindex(pd.DatetimeIndex(trading_days), method="ffill")
    else:
        fg_aligned = pd.Series(50, index=pd.DatetimeIndex(trading_days))

    current_holding = None
    entry_price = None
    last_rotation = -999

    for i in range(10, len(trading_days)):
        date = trading_days[i]
        date_str = date.strftime("%Y-%m-%d")

        # Stop loss
        if current_holding is not None and entry_price is not None:
            if current_holding == "GLD":
                current = float(gld_close.loc[date])
            elif current_holding == "QQQ":
                current = float(qqq_close.loc[date])
            else:
                current = float(xle_close.loc[date])

            pct = (current - entry_price) / entry_price
            if pct <= -0.03:
                portfolio.sell(current_holding, all_shares=True, date=date_str)
                current_holding = None
                entry_price = None
                last_rotation = i
                continue

        # Rotate every 2 days
        if i - last_rotation < 2:
            continue

        fg_val = float(fg_aligned.loc[date]) if date in fg_aligned.index and not pd.isna(fg_aligned.loc[date]) else 50

        gld_mom = float(gld_ret.loc[date]) if date in gld_ret.index and not pd.isna(gld_ret.loc[date]) else 0
        qqq_mom = float(qqq_ret.loc[date]) if date in qqq_ret.index and not pd.isna(qqq_ret.loc[date]) else 0
        xle_mom = float(xle_ret.loc[date]) if date in xle_ret.index and not pd.isna(xle_ret.loc[date]) else 0

        if fg_val < 25:
            target = "GLD"
        elif fg_val > 50:
            target = "QQQ" if qqq_mom > xle_mom else "XLE"
        else:
            moms = {"GLD": gld_mom, "QQQ": qqq_mom, "XLE": xle_mom}
            target = max(moms, key=moms.get)

        if target != current_holding:
            if current_holding is not None:
                portfolio.sell(current_holding, all_shares=True, date=date_str)

            dollars = portfolio.cash * 0.90
            result = portfolio.buy(target, dollars=dollars, date=date_str)
            if result:
                current_holding = target
                entry_price = result["exec_price"]

        last_rotation = i
